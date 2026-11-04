`timescale 1ns / 1ps
`default_nettype none

// Complete short capture through the synthesizable top; source remains continuous.
module tb_capture_stream;
    localparam integer FRAME_WORDS = 7, FRAMES = 12, WORDS = FRAME_WORDS * FRAMES;
    reg clk = 0, resetn = 0, sink_ready = 0, capture_done = 0;
    always #5 clk = !clk;
    wire [31:0] sink_data;
    wire [3:0] sink_keep;
    wire sink_valid, sink_last;
    integer output_words = 0, cycle = 0, capture_end_cycle;
    reg [36:0] held_beat;
    integer capture_file;
    string outdir;
    daq_stream_top dut (
        .aclk(clk), .aresetn(resetn),
        .m_axis_tdata(sink_data), .m_axis_tkeep(sink_keep), .m_axis_tvalid(sink_valid),
        .m_axis_tready(sink_ready), .m_axis_tlast(sink_last)
    );
    always @(negedge clk) sink_ready = !capture_done && (cycle % 11 < 7);
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (resetn && !capture_done) begin
            if (sink_valid && sink_ready) begin
                if (sink_data !== (((output_words / FRAME_WORDS) << 16) | (output_words % FRAME_WORDS)) ||
                    sink_keep !== 4'hf || sink_last !== (output_words % FRAME_WORDS == FRAME_WORDS - 1))
                    $fatal(1, "Capture stream mismatch");
                $fdisplay(capture_file, "%0d,%0d,%08x,%0d,%0d", cycle, output_words,
                          sink_data, sink_keep, sink_last);
                output_words = output_words + 1;
                if (output_words == WORDS) begin
                    capture_done = 1;
                    capture_end_cycle = cycle;
                    $fclose(capture_file);
                    // The top keeps producing; stop accepting and check the next beat holds.
                    @(negedge clk);
                    sink_ready = 0;
                    #1;
                    if (sink_valid !== 1'b1) $fatal(1, "Expected next buffered beat");
                    held_beat = {sink_last, sink_keep, sink_data};
                    repeat (5) begin
                        @(posedge clk);
                        #1;
                        if (sink_valid !== 1'b1 || {sink_last, sink_keep, sink_data} !== held_beat)
                            $fatal(1, "Top output changed after capture backpressure");
                    end
                    $display("PASS top-level RTL capture: %0d frames, %0d words, %0d bytes, capture_end_cycle=%0d; post-capture held beat checked for 5 clocks",
                             FRAMES, WORDS, WORDS * 4, capture_end_cycle);
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
