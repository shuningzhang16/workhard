`timescale 1ns / 1ps
`default_nettype none

module tb_axis_pattern_source;
    parameter integer FRAME_WORDS = 16;
    reg clk = 0;
    always #5 clk = !clk;
    reg resetn = 0;
    reg ready = 0;
    wire [31:0] data;
    wire [3:0] keep;
    wire valid, last;
    axis_pattern_source #(.FRAME_WORDS(FRAME_WORDS)) dut (
        .aclk(clk), .aresetn(resetn), .m_axis_tdata(data),
        .m_axis_tkeep(keep), .m_axis_tvalid(valid),
        .m_axis_tready(ready), .m_axis_tlast(last)
    );

    integer cycle = 0, epoch = -1, accepted = 0;
    integer total_words = 0, total_frames = 0, stalled = 0;
    integer stalled_last = 0, reset_while_stalled = 0, wraps = 0;
    integer consecutive = 0, longest_run = 0;
    integer trace_file, transfer_file, summary_file, ignored, n;
    integer expected_frame, expected_index;
    reg was_reset = 0, held = 0;
    reg [31:0] held_data;
    reg [3:0] held_keep;
    reg held_last;
    reg [31:0] random_state = 32'h1bad_f00d;
    string outdir;
    string phase = "startup_reset";

    // All stimulus changes on falling edges, away from the sampling edge.
    task automatic drive(input bit rst_n, input bit rdy, input integer count);
        repeat (count) begin
            @(negedge clk);
            resetn = rst_n;
            ready = rdy;
        end
    endtask

    // Independent scoreboard: expected data comes only from accepted-word count.
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (!resetn) begin
            if (!was_reset) begin
                epoch = epoch + 1;
                if (held) reset_while_stalled = reset_while_stalled + 1;
            end
            was_reset = 1;
            accepted = 0;
            held = 0;
            consecutive = 0;
            #1;
            if (valid !== 1'b0 || data !== 32'd0)
                $fatal(1, "Reset did not clear valid/sequence/index at cycle %0d", cycle);
        end else begin
            // One rising edge after reset release brings valid high.
            if (!was_reset && valid !== 1'b1)
                $fatal(1, "Source waited for ready or inserted a bubble at cycle %0d", cycle);
            was_reset = 0;
            if (held && (valid !== 1'b1 || data !== held_data ||
                         keep !== held_keep || last !== held_last))
                $fatal(1, "Unaccepted beat changed at cycle %0d", cycle);
            if (valid) begin
                expected_frame = (accepted / FRAME_WORDS) & 16'hffff;
                expected_index = accepted % FRAME_WORDS;
                if (data !== ((expected_frame << 16) | expected_index))
                    $fatal(1, "Data mismatch cycle=%0d got=%08x frame=%0d index=%0d",
                           cycle, data, expected_frame, expected_index);
                if (last !== (expected_index == FRAME_WORDS - 1) || keep !== 4'hf)
                    $fatal(1, "TLAST/TKEEP mismatch cycle=%0d", cycle);
                if (ready) begin
                    // Bound committed raw data; long wrap test is still fully checked.
                    if (total_words < 4096 || (FRAME_WORDS == 1 && accepted >= 65532))
                        $fdisplay(transfer_file, "%0d,%0d,%0d,%08x,%0d,%0d",
                                  cycle, epoch, accepted, data, keep, last);
                    accepted = accepted + 1;
                    total_words = total_words + 1;
                    consecutive = consecutive + 1;
                    if (consecutive > longest_run) longest_run = consecutive;
                    if (last) total_frames = total_frames + 1;
                    if (expected_frame == 65535 && last) wraps = wraps + 1;
                end else begin
                    stalled = stalled + 1;
                    consecutive = 0;
                    if (last) stalled_last = stalled_last + 1;
                end
            end else consecutive = 0;
            held = valid && !ready;
            held_data = data;
            held_keep = keep;
            held_last = last;
            // This row records pre-edge data/handshake, before nonblocking updates.
            if (cycle <= 2048)
                $fdisplay(trace_file, "%0d,%s,%0d,%0d,%0d,%08x,%0d,%0d",
                          cycle, phase, epoch, valid, ready, data, keep, last);
        end
    end

    initial begin
        if (FRAME_WORDS < 1 || FRAME_WORDS > 65536)
            $fatal(1, "FRAME_WORDS must be 1..65536");
        if (!$value$plusargs("OUTDIR=%s", outdir)) outdir = ".";
        trace_file = $fopen({outdir, "/cycles.csv"}, "w");
        transfer_file = $fopen({outdir, "/transfers.csv"}, "w");
        summary_file = $fopen({outdir, "/summary.json"}, "w");
        if (!trace_file || !transfer_file || !summary_file) $fatal(1, "Cannot open outputs");
        $fdisplay(trace_file, "cycle,phase,epoch,valid,ready,data_hex,keep,last");
        $fdisplay(transfer_file, "cycle,epoch,ordinal,data_hex,keep,last");
        drive(0, 0, 3);
        phase = "ready_low_at_start";
        drive(1, 0, 12);
        phase = "continuous";
        drive(1, 1, FRAME_WORDS * 4 + 3);

        // Explicitly hold TLAST for multiple cycles, then accept it.
        @(negedge clk);
        while (!last) @(negedge clk);
        phase = "hold_last";
        ready = 0;
        repeat (9) @(negedge clk);
        ready = 1;
        drive(1, 1, FRAME_WORDS * 2 + 1);

        phase = "deterministic_random_backpressure";
        for (n = 0; n < 1000; n = n + 1) begin
            random_state = random_state ^ (random_state << 13);
            random_state = random_state ^ (random_state >> 17);
            random_state = random_state ^ (random_state << 5);
            drive(1, random_state[0] | random_state[1], 1);
        end

        // Reset while an unaccepted word is held; old partial frame is discarded.
        phase = "reset_held_word";
        drive(1, 0, 5);
        drive(0, 0, 3);
        drive(1, 0, 7);
        phase = "restart";
        drive(1, 1, FRAME_WORDS * 6 + 2);
        // The one-word test naturally crosses the 16-bit frame counter wrap.
        if (FRAME_WORDS == 1) begin
            phase = "sequence_wrap";
            drive(1, 1, 65540);
        end
        @(negedge clk);
        if (stalled_last < 9 || reset_while_stalled != 1 ||
            longest_run < FRAME_WORDS * 4 || total_frames < 10)
            $fatal(1, "Required stimulus coverage missing");
        if (FRAME_WORDS == 1 && wraps != 1) $fatal(1, "Frame wrap not exercised");
        $fdisplay(summary_file,
            "{\"result\":\"PASS\",\"frame_words\":%0d,\"cycles\":%0d,\"accepted_words\":%0d,\"complete_frames\":%0d,\"stalled_cycles\":%0d,\"stalled_last_cycles\":%0d,\"reset_while_stalled\":%0d,\"longest_continuous_run\":%0d,\"sequence_wraps\":%0d}",
            FRAME_WORDS, cycle, total_words, total_frames, stalled,
            stalled_last, reset_while_stalled, longest_run, wraps);
        $display("PASS frame_words=%0d accepted=%0d frames=%0d stalls=%0d held_last=%0d resets_held=%0d wrap=%0d",
                 FRAME_WORDS, total_words, total_frames, stalled,
                 stalled_last, reset_while_stalled, wraps);
        $fclose(trace_file);
        $fclose(transfer_file);
        $fclose(summary_file);
        $finish;
    end

    initial begin
        #20000000;
        $fatal(1, "Testbench timeout");
    end
endmodule

`default_nettype wire
