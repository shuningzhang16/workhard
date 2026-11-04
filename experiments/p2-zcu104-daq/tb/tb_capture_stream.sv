`timescale 1ns / 1ps
`default_nettype none

// Complete short capture for the host C validator, without a mid-capture reset.
module tb_capture_stream;
    localparam integer FRAME_WORDS = 7, FRAMES = 12, WORDS = FRAME_WORDS * FRAMES;
    reg clk = 0, resetn = 0, sink_ready = 0;
    always #5 clk = !clk;
    wire [31:0] source_data, sink_data;
    wire [3:0] source_keep, sink_keep;
    wire source_valid, source_ready, source_last, fifo_ready, sink_valid, sink_last;
    integer input_words = 0, output_words = 0, cycle = 0;
    integer capture_file;
    string outdir;
    wire allow_input = input_words < WORDS;
    assign source_ready = fifo_ready && allow_input;
    axis_pattern_source #(.FRAME_WORDS(FRAME_WORDS)) source (
        .aclk(clk), .aresetn(resetn), .m_axis_tdata(source_data),
        .m_axis_tkeep(source_keep), .m_axis_tvalid(source_valid),
        .m_axis_tready(source_ready), .m_axis_tlast(source_last)
    );
    axis_sync_fifo #(.DEPTH(3)) fifo (
        .aclk(clk), .aresetn(resetn), .s_axis_tdata(source_data),
        .s_axis_tkeep(source_keep), .s_axis_tvalid(source_valid && allow_input),
        .s_axis_tready(fifo_ready), .s_axis_tlast(source_last),
        .m_axis_tdata(sink_data), .m_axis_tkeep(sink_keep), .m_axis_tvalid(sink_valid),
        .m_axis_tready(sink_ready), .m_axis_tlast(sink_last)
    );
    always @(negedge clk) sink_ready = (cycle % 11 < 7);
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (!resetn) input_words <= 0;
        else begin
            if (source_valid && source_ready) input_words <= input_words + 1;
            if (sink_valid && sink_ready) begin
                if (sink_data !== (((output_words / FRAME_WORDS) << 16) | (output_words % FRAME_WORDS)) ||
                    sink_keep !== 4'hf || sink_last !== (output_words % FRAME_WORDS == FRAME_WORDS - 1))
                    $fatal(1, "Capture stream mismatch");
                $fdisplay(capture_file, "%0d,%0d,%08x,%0d,%0d", cycle, output_words,
                          sink_data, sink_keep, sink_last);
                output_words = output_words + 1;
                if (output_words == WORDS) begin
                    #1;
                    if (input_words != WORDS || sink_valid !== 1'b0)
                        $fatal(1, "Capture did not fully drain");
                    $fclose(capture_file);
                    $display("PASS complete RTL capture: %0d frames, %0d words, %0d bytes, %0d cycles",
                             FRAMES, WORDS, WORDS * 4, cycle);
                    $finish;
                end
            end
        end
    end
    initial begin
        if (!$value$plusargs("OUTDIR=%s", outdir)) outdir = ".";
        capture_file = $fopen({outdir, "/rtl_capture.csv"}, "w");
        if (!capture_file) $fatal(1, "Cannot open capture output");
        $fdisplay(capture_file, "cycle,ordinal,data_hex,keep,last");
        repeat (3) @(negedge clk);
        resetn = 1;
    end
    initial begin
        #100000;
        $fatal(1, "Capture timeout");
    end
endmodule

`default_nettype wire
