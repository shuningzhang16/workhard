`timescale 1ns / 1ps
`default_nettype none

// Synthesizable source + single-clock FIFO. Continuous until reset/backpressure.
// No DMA, PS registers or clock-domain crossing is implemented here.
module daq_stream_top #(
    parameter integer FRAME_WORDS = 7,
    parameter integer FIFO_DEPTH = 3
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF M_AXIS, ASSOCIATED_RESET aresetn" *)
    input  wire        aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        aresetn,
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
    wire [31:0] data;
    wire [3:0] keep;
    wire valid, ready, last;

    axis_pattern_source #(.FRAME_WORDS(FRAME_WORDS)) source (
        .aclk(aclk), .aresetn(aresetn), .m_axis_tdata(data),
        .m_axis_tkeep(keep), .m_axis_tvalid(valid),
        .m_axis_tready(ready), .m_axis_tlast(last)
    );
    axis_sync_fifo #(.DEPTH(FIFO_DEPTH)) fifo (
        .aclk(aclk), .aresetn(aresetn), .s_axis_tdata(data),
        .s_axis_tkeep(keep), .s_axis_tvalid(valid), .s_axis_tready(ready), .s_axis_tlast(last),
        .m_axis_tdata(m_axis_tdata), .m_axis_tkeep(m_axis_tkeep),
        .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready), .m_axis_tlast(m_axis_tlast)
    );
endmodule

`default_nettype wire
