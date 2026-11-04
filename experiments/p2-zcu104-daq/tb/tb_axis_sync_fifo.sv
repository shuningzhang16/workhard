`timescale 1ns / 1ps
`default_nettype none

module tb_axis_sync_fifo;
    parameter integer DEPTH = 16;
    localparam integer FRAME_WORDS = 7;
    reg clk = 0;
    always #5 clk = !clk;
    reg resetn = 0, feed_enable = 0, out_ready = 0;
    wire [31:0] source_data, out_data;
    wire [3:0] source_keep, in_keep, out_keep;
    wire source_valid, source_last, in_valid, in_ready, out_valid, out_last;
    wire source_ready = in_ready && feed_enable;
    assign in_valid = source_valid && feed_enable;
    // Test-only byte-enable variation: f, 7, 3, 1. The source RTL is unchanged.
    assign in_keep = 4'hf >> source_data[1:0];
    wire [36:0] in_beat = {source_last, in_keep, source_data};
    wire [36:0] out_beat = {out_last, out_keep, out_data};
    axis_pattern_source #(.FRAME_WORDS(FRAME_WORDS)) source (
        .aclk(clk), .aresetn(resetn), .m_axis_tdata(source_data),
        .m_axis_tkeep(source_keep), .m_axis_tvalid(source_valid),
        .m_axis_tready(source_ready), .m_axis_tlast(source_last)
    );
    axis_sync_fifo #(.DEPTH(DEPTH)) dut (
        .aclk(clk), .aresetn(resetn), .s_axis_tdata(source_data),
        .s_axis_tkeep(in_keep), .s_axis_tvalid(in_valid),
        .s_axis_tready(in_ready), .s_axis_tlast(source_last),
        .m_axis_tdata(out_data), .m_axis_tkeep(out_keep),
        .m_axis_tvalid(out_valid), .m_axis_tready(out_ready), .m_axis_tlast(out_last)
    );

    // Independent unbounded queue: no DUT pointers/count are read by the checker.
    reg [36:0] reference_queue [$];
    reg [36:0] expected_beat, held_input, held_output;
    reg input_held = 0, output_held = 0, was_reset = 0;
    reg push, pop;
    reg [31:0] random_state = 32'h31415926;
    integer cycle = 0, epoch = -1, epoch_input = 0;
    integer inputs = 0, outputs = 0, discarded = 0, reset_nonempty = 0;
    integer peak = 0, input_stalls = 0, output_stalls = 0, last_stalls = 0;
    integer empty_cycles = 0, full_cycles = 0, simultaneous = 0, full_exchange = 0;
    integer input_frames = 0, output_frames = 0, steady_cycles = 0, steady_outputs = 0;
    integer before_count, expected_data, trace_file, summary_file, n;
    string outdir, phase = "startup_reset";

    // Feed gating only inserts legal idle cycles: a presented stalled beat stays valid.
    task automatic drive(input string label, input bit rst_n,
                         input bit send, input bit receive, input integer cycles);
        repeat (cycles) begin
            @(negedge clk);
            phase = label;
            resetn = rst_n;
            out_ready = receive;
            if (!rst_n || !input_held) feed_enable = send;
        end
    endtask

    always @(posedge clk) begin
        cycle = cycle + 1;
        before_count = reference_queue.size();
        if (!resetn) begin
            if (!was_reset) begin
                epoch = epoch + 1;
                if (before_count != 0) reset_nonempty = reset_nonempty + 1;
                discarded = discarded + before_count;
            end
            reference_queue.delete();
            epoch_input = 0;
            input_held = 0;
            output_held = 0;
            was_reset = 1;
            #1;
            if (out_valid !== 1'b0 || in_ready !== 1'b1)
                $fatal(1, "FIFO did not become empty on reset");
        end else begin
            was_reset = 0;
            if (out_valid !== (before_count != 0))
                $fatal(1, "Valid/empty mismatch cycle=%0d occupancy=%0d", cycle, before_count);
            if (in_ready !== ((before_count < DEPTH) || ((before_count > 0) && out_ready)))
                $fatal(1, "Ready/full mismatch cycle=%0d occupancy=%0d", cycle, before_count);
            if (input_held && (in_valid !== 1'b1 || in_beat !== held_input))
                $fatal(1, "Illegal test stimulus: input changed while stalled");
            if (output_held && (out_valid !== 1'b1 || out_beat !== held_output))
                $fatal(1, "FIFO output changed while stalled at cycle %0d", cycle);
            // Check every visible output, including cycles not accepted by the sink.
            if (before_count > 0 && out_beat !== reference_queue[0])
                $fatal(1, "Head mismatch cycle=%0d got=%010x expected=%010x",
                       cycle, out_beat, reference_queue[0]);
            push = in_valid && in_ready;
            pop = out_valid && out_ready;
            // Pop before push: an empty FIFO must not bypass a new beat in this cycle.
            if (pop) begin
                expected_beat = reference_queue.pop_front();
                if (out_beat !== expected_beat) $fatal(1, "Output order/sideband mismatch");
                outputs = outputs + 1;
                if (out_last) output_frames = output_frames + 1;
            end
            if (push) begin
                expected_data = ((epoch_input / FRAME_WORDS) << 16) | (epoch_input % FRAME_WORDS);
                if (source_data !== expected_data || source_last !== (epoch_input % FRAME_WORDS == FRAME_WORDS-1))
                    $fatal(1, "Source sequence mismatch");
                reference_queue.push_back(in_beat);
                inputs = inputs + 1;
                epoch_input = epoch_input + 1;
                if (source_last) input_frames = input_frames + 1;
            end
            if (reference_queue.size() > DEPTH) $fatal(1, "FIFO overflow");
            if (reference_queue.size() > peak) peak = reference_queue.size();
            if (before_count == 0) empty_cycles = empty_cycles + 1;
            if (before_count == DEPTH) full_cycles = full_cycles + 1;
            if (push && pop) begin
                simultaneous = simultaneous + 1;
                if (before_count == DEPTH) full_exchange = full_exchange + 1;
            end
            if (in_valid && !in_ready) input_stalls = input_stalls + 1;
            if (out_valid && !out_ready) begin
                output_stalls = output_stalls + 1;
                if (out_last) last_stalls = last_stalls + 1;
            end
            if (phase == "full_exchange") begin
                steady_cycles = steady_cycles + 1;
                if (pop) steady_outputs = steady_outputs + 1;
                if (!push || !pop) $fatal(1, "Bubble during full FIFO simultaneous transfers");
            end
            input_held = in_valid && !in_ready;
            output_held = out_valid && !out_ready;
            held_input = in_beat;
            held_output = out_beat;
        end
        if (inputs != outputs + discarded + reference_queue.size())
            $fatal(1, "Conservation failure: in != out + reset_discard + pending");
        // Limited raw traces include fill/full/exchange/last-stall, reset and drain.
        // Interface signals are meaningful only when resetn=1 and valid=1.
        if (cycle <= 512 || phase == "reset_buffered" || phase == "final_drain")
            $fdisplay(trace_file, "%0d,%s,%0d,%0d,%0d,%0d,%0d,%0d,%08x,%0d,%0d,%0d,%0d,%08x,%0d,%0d,%0d",
                      cycle, phase, epoch, resetn, before_count, reference_queue.size(),
                      in_valid, in_ready, source_data, in_keep, source_last,
                      out_valid, out_ready, out_data, out_keep, out_last, discarded);
    end

    initial begin
        if (DEPTH < 1) $fatal(1, "DEPTH must be positive");
        if (!$value$plusargs("OUTDIR=%s", outdir)) outdir = ".";
        trace_file = $fopen({outdir, "/cycles.csv"}, "w");
        summary_file = $fopen({outdir, "/summary.json"}, "w");
        if (!trace_file || !summary_file) $fatal(1, "Cannot open outputs");
        $fdisplay(trace_file, "cycle,phase,epoch,resetn,occupancy_before,occupancy_after,in_valid,in_ready,in_data_hex,in_keep,in_last,out_valid,out_ready,out_data_hex,out_keep,out_last,reset_discarded_total");
        drive("startup_reset", 0, 0, 0, 3);
        drive("empty", 1, 0, 1, 8);
        drive("fill_and_stall", 1, 1, 0, DEPTH + 8);
        drive("full_exchange", 1, 1, 1, DEPTH * 4 + 8);
        drive("drain_to_empty", 1, 0, 1, DEPTH + 8);
        drive("continuous", 1, 1, 1, DEPTH * 4 + 13);
        @(negedge clk);
        while (!(out_valid && out_last)) @(negedge clk);
        phase = "hold_last";
        out_ready = 0;
        repeat (8) @(negedge clk);
        for (n = 0; n < 1000; n = n + 1) begin
            random_state = random_state ^ (random_state << 13);
            random_state = random_state ^ (random_state >> 17);
            random_state = random_state ^ (random_state << 5);
            drive("random", 1, random_state[0] | random_state[1], random_state[2] | random_state[3], 1);
        end
        drive("fill_before_reset", 1, 1, 0, DEPTH + 8);
        drive("reset_buffered", 0, 0, 0, 3);
        drive("empty_after_reset", 1, 0, 1, 3);
        drive("restart", 1, 1, 1, DEPTH * 2 + 30);
        drive("final_drain", 1, 0, 1, DEPTH + 8);
        @(negedge clk);
        if (reference_queue.size() != 0 || inputs != outputs + discarded)
            $fatal(1, "Final drain/conservation failure");
        if (peak != DEPTH || discarded != DEPTH || reset_nonempty != 1 ||
            full_exchange < DEPTH * 4 || inputs < DEPTH * 8 || outputs < DEPTH * 8 ||
            input_stalls == 0 || last_stalls < 8 || empty_cycles < 8 || steady_cycles == 0)
            $fatal(1, "Required FIFO stimulus coverage missing");
        $fdisplay(summary_file,
            "{\"result\":\"PASS\",\"depth\":%0d,\"frame_words\":%0d,\"clock_period_ns\":10,\"cycles\":%0d,\"input_handshakes\":%0d,\"output_handshakes\":%0d,\"reset_discarded\":%0d,\"pending\":%0d,\"peak_occupancy\":%0d,\"input_stall_cycles\":%0d,\"output_stall_cycles\":%0d,\"last_stall_cycles\":%0d,\"empty_cycles\":%0d,\"full_cycles\":%0d,\"simultaneous\":%0d,\"full_simultaneous\":%0d,\"input_tlast_handshakes\":%0d,\"output_tlast_handshakes\":%0d,\"steady_cycles\":%0d,\"steady_output_handshakes\":%0d}",
            DEPTH, FRAME_WORDS, cycle, inputs, outputs, discarded, reference_queue.size(),
            peak, input_stalls, output_stalls, last_stalls, empty_cycles, full_cycles,
            simultaneous, full_exchange, input_frames, output_frames, steady_cycles, steady_outputs);
        $display("PASS depth=%0d in=%0d out=%0d reset_discard=%0d pending=%0d peak=%0d full_exchange=%0d steady=%0d/%0d",
                 DEPTH, inputs, outputs, discarded, reference_queue.size(), peak, full_exchange,
                 steady_outputs, steady_cycles);
        $fclose(trace_file);
        $fclose(summary_file);
        $finish;
    end

    initial begin
        #5000000;
        $fatal(1, "FIFO testbench timeout");
    end
endmodule

`default_nettype wire
