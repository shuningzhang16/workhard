`timescale 1ns / 1ps
`default_nettype none

// Independent controlled wrapper; daq_stream_top and its tests remain unchanged.
// One outstanding AXI-Lite write and one read, independently. 64-byte aperture.
module daq_axi_lite #(
    parameter integer FRAME_WORDS = 7,
    parameter integer FIFO_DEPTH = 3
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI:M_AXIS, ASSOCIATED_RESET aresetn" *)
    input  wire        aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 stream_resetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        stream_resetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 6, READ_WRITE_MODE READ_WRITE" *)
    input  wire [5:0]  s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input  wire [2:0]  s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input  wire        s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output wire        s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input  wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input  wire [3:0]  s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input  wire        s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output wire        s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output reg  [1:0]  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output reg         s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input  wire        s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input  wire [5:0]  s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input  wire [2:0]  s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input  wire        s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output wire        s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output reg  [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output reg  [1:0]  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output reg         s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input  wire        s_axi_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *)
    output wire [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *)
    output wire [3:0]  m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *)
    output wire        m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *)
    input  wire        m_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *)
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
        .aclk(aclk), .aresetn(aresetn && stream_resetn && !restart_pulse),
        .m_axis_tdata(m_axis_tdata), .m_axis_tkeep(m_axis_tkeep),
        .m_axis_tvalid(stream_valid), .m_axis_tready(m_axis_tready && running && stream_resetn),
        .m_axis_tlast(m_axis_tlast)
    );
    // Running only falls on an accepted TLAST, so a held valid beat is never
    // withdrawn by STOP. Pausing preserves any prefetched next-frame words.
    assign m_axis_tvalid = stream_valid && running && stream_resetn;

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
                    CONTROL: if (write_strobe[0] && write_data[0] && !stream_resetn)
                                 s_axi_bresp <= SLVERR;
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
                    STATUS: s_axi_rdata <= {29'd0, !stream_resetn, stop_pending, running};
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
            // DMA resets only the acquisition state, never the AXI-Lite channel
            // buffers/responses. Control MMIO remains usable while DMA is reset.
            if (!stream_resetn) begin
                running <= 0;
                stop_pending <= 0;
                restart_pulse <= 0;
                words <= 0;
                frames <= 0;
                stalls <= 0;
            end
        end
    end
    // AxPROT has no access-control role in this local experiment peripheral.
endmodule

`default_nettype wire
