`timescale 1ns / 1ps
`default_nettype none

// Independent controlled wrapper; daq_stream_top and its tests remain unchanged.
// One outstanding AXI-Lite write and one read, independently. 64-byte aperture.
module daq_axi_lite #(
    parameter integer FRAME_WORDS = 7,
    parameter integer FIFO_DEPTH = 3
) (
    input  wire        aclk,
    input  wire        aresetn,
    input  wire [5:0]  s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    output reg  [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [5:0]  s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output reg  [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,
    output wire [31:0] m_axis_tdata,
    output wire [3:0]  m_axis_tkeep,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);
    localparam [5:0] CONTROL = 6'h00, STATUS = 6'h04, COMMAND = 6'h08,
                     WORDS = 6'h0c, FRAMES = 6'h10, STALLS = 6'h14;
    localparam [1:0] OKAY = 2'b00, SLVERR = 2'b10;
    reg aw_saved, w_saved;
    reg [5:0] write_address;
    reg [31:0] write_data;
    reg [3:0] write_strobe;
    reg running, stop_pending, restart_pulse;
    reg [31:0] words, frames, stalls;
    wire stream_valid;
    wire transfer = m_axis_tvalid && m_axis_tready;

    // AW and W may arrive in either order. No second transaction is accepted
    // until the prior B response is consumed; read and write paths stay separate.
    assign s_axi_awready = aresetn && !aw_saved && !s_axi_bvalid;
    assign s_axi_wready = aresetn && !w_saved && !s_axi_bvalid;
    assign s_axi_arready = aresetn && !s_axi_rvalid;
    wire commit_write = aw_saved && w_saved && !s_axi_bvalid;
    wire control_write = commit_write && write_address == CONTROL && write_strobe[0];
    wire command_write = commit_write && write_address == COMMAND && write_strobe[0];
    wire restart_command = command_write && write_data[0] && !running;
    wire clear_command = command_write && write_data[1] && !running;
    wire stop_command = control_write && !write_data[0];

    daq_stream_top #(.FRAME_WORDS(FRAME_WORDS), .FIFO_DEPTH(FIFO_DEPTH)) stream (
        .aclk(aclk), .aresetn(aresetn && !restart_pulse),
        .m_axis_tdata(m_axis_tdata), .m_axis_tkeep(m_axis_tkeep),
        .m_axis_tvalid(stream_valid), .m_axis_tready(m_axis_tready && running),
        .m_axis_tlast(m_axis_tlast)
    );
    // Running only falls on an accepted TLAST, so a held valid beat is never
    // withdrawn by STOP. Pausing preserves any prefetched next-frame words.
    assign m_axis_tvalid = stream_valid && running;

    always @(posedge aclk) begin
        if (!aresetn) begin
            aw_saved <= 0;
            w_saved <= 0;
            write_address <= 0;
            write_data <= 0;
            write_strobe <= 0;
            s_axi_bvalid <= 0;
            s_axi_bresp <= OKAY;
            s_axi_rvalid <= 0;
            s_axi_rdata <= 0;
            s_axi_rresp <= OKAY;
            running <= 0;
            stop_pending <= 0;
            restart_pulse <= 0;
            words <= 0;
            frames <= 0;
            stalls <= 0;
        end else begin
            restart_pulse <= 0;
            if (s_axi_awvalid && s_axi_awready) begin
                aw_saved <= 1;
                write_address <= s_axi_awaddr;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                w_saved <= 1;
                write_data <= s_axi_wdata;
                write_strobe <= s_axi_wstrb;
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            if (commit_write) begin
                aw_saved <= 0;
                w_saved <= 0;
                s_axi_bvalid <= 1;
                s_axi_bresp <= OKAY;
                case (write_address)
                    CONTROL: begin end
                    COMMAND: if (write_strobe[0] && (|write_data[1:0]) && running)
                                 s_axi_bresp <= SLVERR;
                    default: s_axi_bresp <= SLVERR;
                endcase
            end

            if (control_write) begin
                if (write_data[0]) begin
                    running <= 1;
                    stop_pending <= 0;       // START also cancels a pending STOP.
                end else if (running) stop_pending <= 1;
            end
            // A STOP committed on the TLAST handshake stops at that boundary.
            // A simultaneous START cancels an earlier pending stop.
            if (running && transfer && m_axis_tlast &&
                (stop_pending || stop_command) && !(control_write && write_data[0])) begin
                running <= 0;
                stop_pending <= 0;
            end
            if (restart_command) restart_pulse <= 1;
            if (restart_command || clear_command) begin
                words <= 0;
                frames <= 0;
                stalls <= 0;
            end else begin
                if (transfer) begin
                    words <= words + 1'b1;
                    if (m_axis_tlast) frames <= frames + 1'b1;
                end
                if (m_axis_tvalid && !m_axis_tready) stalls <= stalls + 1'b1;
            end

            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 0;
            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1;
                s_axi_rresp <= OKAY;
                // Snapshot at AR acceptance; held unchanged until R handshake.
                // Counts exclude transfers/stalls on this same clock edge.
                case (s_axi_araddr)
                    CONTROL: s_axi_rdata <= {31'd0, running && !stop_pending};
                    STATUS: s_axi_rdata <= {30'd0, stop_pending, running};
                    COMMAND: s_axi_rdata <= 0;
                    WORDS: s_axi_rdata <= words;
                    FRAMES: s_axi_rdata <= frames;
                    STALLS: s_axi_rdata <= stalls;
                    default: begin
                        s_axi_rdata <= 0;
                        s_axi_rresp <= SLVERR;
                    end
                endcase
            end
        end
    end
    // AxPROT has no access-control role in this local experiment peripheral.
endmodule

`default_nettype wire
