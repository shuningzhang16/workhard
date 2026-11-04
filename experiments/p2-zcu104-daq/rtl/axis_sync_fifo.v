`timescale 1ns / 1ps
`default_nettype none

// Small single-clock FIFO; DEPTH >= 1, including non-powers of two.
// Synchronous active-low reset discards buffered beats.
// Packed storage keeps data, byte enables and frame boundary together.
// Asynchronous memory read: this is not a block-RAM-specific implementation.
module axis_sync_fifo #(
    parameter integer DEPTH = 16
) (
    input  wire        aclk,
    input  wire        aresetn,
    input  wire [31:0] s_axis_tdata,
    input  wire [3:0]  s_axis_tkeep,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,
    output wire [31:0] m_axis_tdata,
    output wire [3:0]  m_axis_tkeep,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);
    localparam integer PTR_WIDTH = (DEPTH > 1) ? $clog2(DEPTH) : 1;
    localparam integer COUNT_WIDTH = $clog2(DEPTH + 1);
    reg [36:0] memory [0:DEPTH-1];
    reg [PTR_WIDTH-1:0] write_ptr, read_ptr;
    reg [COUNT_WIDTH-1:0] count;

    assign m_axis_tvalid = (count != 0);
    // A full FIFO can replace the beat being accepted in this same cycle.
    assign s_axis_tready = (count < DEPTH) ||
                          (m_axis_tvalid && m_axis_tready);
    assign {m_axis_tlast, m_axis_tkeep, m_axis_tdata} = memory[read_ptr];
    wire push = s_axis_tvalid && s_axis_tready;
    wire pop = m_axis_tvalid && m_axis_tready;

    always @(posedge aclk) begin
        if (!aresetn) begin
            count <= 0;
            write_ptr <= 0;
            read_ptr <= 0;
        end else begin
            if (push) begin
                memory[write_ptr] <= {s_axis_tlast, s_axis_tkeep, s_axis_tdata};
                write_ptr <= (write_ptr == DEPTH - 1) ? 0 : write_ptr + 1'b1;
            end
            if (pop)
                read_ptr <= (read_ptr == DEPTH - 1) ? 0 : read_ptr + 1'b1;
            case ({push, pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule

`default_nettype wire
