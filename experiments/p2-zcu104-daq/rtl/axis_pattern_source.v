`timescale 1ns / 1ps
`default_nettype none

// Internal test source, not an ADC interface.
// FRAME_WORDS: 1..65536. Reset is active-low and synchronous to aclk.
// Each accepted word is {16-bit frame sequence, 16-bit word index}.
// Sequence wraps at 65536 frames. Reset aborts any partial frame.
module axis_pattern_source #(
    parameter integer FRAME_WORDS = 16
) (
    input  wire        aclk,
    input  wire        aresetn,
    output wire [31:0] m_axis_tdata,
    output wire [3:0]  m_axis_tkeep,
    output reg         m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);
    reg [15:0] frame_sequence;
    reg [15:0] word_index;

    assign m_axis_tdata = {frame_sequence, word_index};
    assign m_axis_tkeep = 4'b1111;
    assign m_axis_tlast = (word_index == FRAME_WORDS - 1);

    always @(posedge aclk) begin
        if (!aresetn) begin
            m_axis_tvalid <= 1'b0;
            frame_sequence <= 16'd0;
            word_index <= 16'd0;
        end else begin
            // Do not wait for ready to assert valid.
            m_axis_tvalid <= 1'b1;
            if (m_axis_tvalid && m_axis_tready) begin
                if (m_axis_tlast) begin
                    word_index <= 16'd0;
                    frame_sequence <= frame_sequence + 16'd1;
                end else begin
                    word_index <= word_index + 16'd1;
                end
            end
        end
    end
endmodule

`default_nettype wire
