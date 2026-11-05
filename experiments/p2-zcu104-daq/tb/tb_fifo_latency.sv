`timescale 1ns / 1ps
`default_nettype none

// Finite interface measurements. No internal DUT occupancy/pointer is observed.
module tb_fifo_latency;
    parameter integer DEPTH = 3;
    parameter integer BACKPRESSURE = 1;
    reg clk = 0, resetn = 0, feed_enable = 0, out_ready = 0;
    always #5 clk = !clk;
    wire [31:0] in_data, out_data;
    wire [3:0] in_keep, out_keep;
    wire source_valid, in_ready, in_last, out_valid, out_last;
    wire in_valid = source_valid && feed_enable;
    wire [36:0] in_beat = {in_last, in_keep, in_data};
    wire [36:0] out_beat = {out_last, out_keep, out_data};
    axis_pattern_source #(.FRAME_WORDS(7)) source (
        .aclk(clk), .aresetn(resetn), .m_axis_tdata(in_data),
        .m_axis_tkeep(in_keep), .m_axis_tvalid(source_valid),
        .m_axis_tready(in_ready && feed_enable), .m_axis_tlast(in_last)
    );
    axis_sync_fifo #(.DEPTH(DEPTH)) dut (
        .aclk(clk), .aresetn(resetn), .s_axis_tdata(in_data),
        .s_axis_tkeep(in_keep), .s_axis_tvalid(in_valid),
        .s_axis_tready(in_ready), .s_axis_tlast(in_last),
        .m_axis_tdata(out_data), .m_axis_tkeep(out_keep),
        .m_axis_tvalid(out_valid), .m_axis_tready(out_ready), .m_axis_tlast(out_last)
    );

    reg [36:0] beats [$];
    integer accepted_cycles [$], offered_cycles [$], accepted_ids [$];
    reg [36:0] expected, held_input, held_output;
    reg input_held = 0, output_held = 0, was_reset = 0, push, pop;
    integer cycle = 0, epoch = -1, epoch_input = 0;
    integer accepted = 0, emitted = 0, discarded = 0, peak = 0, source_stalls = 0;
    integer latency_sum = 0, latency_min = 2147483647, latency_max = 0;
    integer offer_cycle = 0, epoch_output = 0, epoch_peak = 0, epoch_stalls = 0;
    integer before_count, start_cycle, first_cycle, beat_id, latency;
    integer trace_file, event_file, epoch_file, summary_file;
    string outdir, phase = "startup_reset";

    task automatic drive(input string label, input bit rst_n,
                         input bit send, input bit receive, input integer cycles);
        repeat (cycles) begin
            @(negedge clk);
            phase = label;
            resetn = rst_n;
            out_ready = receive;
            // A stalled, presented beat must remain valid until accepted or reset.
            if (!rst_n || !input_held) feed_enable = send;
        end
    endtask

    task automatic flow;
        for (integer i = 0; i < 64; i = i + 1)
            drive("flow", 1, 1, !BACKPRESSURE || (i % 8 < 3), 1);
    endtask

    always @(posedge clk) begin
        cycle = cycle + 1;
        before_count = beats.size();
        push = 0;
        pop = 0;
        if (!resetn) begin
            if (!was_reset) begin
                if (epoch >= 0) begin
                    if (epoch_input != epoch_output + before_count) $fatal(1, "Epoch conservation failed");
                    $fdisplay(epoch_file, "%0d,reset,%0d,%0d,%0d,%0d,0,%0d,%0d,%0d",
                              epoch, cycle, epoch_input, epoch_output, before_count,
                              epoch_peak, epoch_stalls, input_held);
                end
                epoch = epoch + 1;
            end
            while (beats.size() != 0) begin
                expected = beats.pop_front();
                start_cycle = accepted_cycles.pop_front();
                first_cycle = offered_cycles.pop_front();
                beat_id = accepted_ids.pop_front();
                // A reset discard has residence time but no delivery latency.
                $fdisplay(event_file, "%0d,%0d,%08x,%0d,%0d,,%0d,RESET_DISCARD,%0d,,",
                          beat_id, epoch - 1, expected[31:0], first_cycle, start_cycle,
                          cycle, start_cycle - first_cycle);
                discarded = discarded + 1;
            end
            epoch_input = 0;
            epoch_output = 0;
            epoch_peak = 0;
            epoch_stalls = 0;
            offer_cycle = 0;
            input_held = 0;
            output_held = 0;
            was_reset = 1;
        end else begin
            was_reset = 0;
            if (out_valid !== (before_count != 0) ||
                in_ready !== ((before_count < DEPTH) || (before_count > 0 && out_ready)))
                $fatal(1, "Interface occupancy mismatch cycle=%0d", cycle);
            if (input_held && (in_valid !== 1'b1 || in_beat !== held_input))
                $fatal(1, "Source changed a stalled beat");
            if (output_held && (out_valid !== 1'b1 || out_beat !== held_output))
                $fatal(1, "FIFO changed a stalled beat");
            if (before_count > 0 && out_beat !== beats[0])
                $fatal(1, "FIFO head/payload/sideband mismatch");
            // First public input VALID sample for this beat, before READY accepts it.
            if (!in_valid) offer_cycle = 0;
            else if (!input_held) offer_cycle = cycle;
            push = in_valid && in_ready;
            pop = out_valid && out_ready;
            // Pop first: input accepted at this edge cannot bypass an empty FIFO.
            if (pop) begin
                expected = beats.pop_front();
                start_cycle = accepted_cycles.pop_front();
                first_cycle = offered_cycles.pop_front();
                beat_id = accepted_ids.pop_front();
                latency = cycle - start_cycle;
                if (out_beat !== expected || latency < 1) $fatal(1, "Output mismatch");
                emitted = emitted + 1;
                epoch_output = epoch_output + 1;
                latency_sum = latency_sum + latency;
                if (latency < latency_min) latency_min = latency;
                if (latency > latency_max) latency_max = latency;
                $fdisplay(event_file, "%0d,%0d,%08x,%0d,%0d,%0d,,OUTPUT,%0d,%0d,%0d",
                          beat_id, epoch, out_data, first_cycle, start_cycle, cycle,
                          start_cycle - first_cycle, latency, cycle - first_cycle);
            end
            if (push) begin
                if (in_data !== (((epoch_input / 7) << 16) | (epoch_input % 7)) ||
                    in_keep !== 4'hf || in_last !== (epoch_input % 7 == 6))
                    $fatal(1, "Source protocol mismatch");
                beats.push_back(in_beat);
                accepted_cycles.push_back(cycle);
                offered_cycles.push_back(offer_cycle);
                accepted_ids.push_back(accepted);
                accepted = accepted + 1;
                epoch_input = epoch_input + 1;
            end
            if (beats.size() > DEPTH) $fatal(1, "FIFO exceeded capacity");
            if (beats.size() > peak) peak = beats.size();
            if (beats.size() > epoch_peak) epoch_peak = beats.size();
            if (in_valid && !in_ready) begin
                source_stalls = source_stalls + 1;
                epoch_stalls = epoch_stalls + 1;
            end
            input_held = in_valid && !in_ready;
            output_held = out_valid && !out_ready;
            held_input = in_beat;
            held_output = out_beat;
        end
        if (accepted != emitted + discarded + beats.size()) $fatal(1, "Conservation failed");
        // All interface fields are sampled before this rising edge updates the DUT.
        $fdisplay(trace_file, "%0d,%s,%0d,%0d,%0d,%0d,%08x,%0d,%0d,%0d,%0d,%08x,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                  cycle, phase, epoch, resetn, in_valid, in_ready, in_data, in_keep, in_last,
                  out_valid, out_ready, out_data, out_keep, out_last, push, pop,
                  before_count, beats.size(), accepted, emitted, discarded, peak, source_stalls, offer_cycle);
    end

    initial begin
        if (!$value$plusargs("OUTDIR=%s", outdir)) outdir = ".";
        trace_file = $fopen({outdir, "/cycles.csv"}, "w");
        event_file = $fopen({outdir, "/beat_events.csv"}, "w");
        epoch_file = $fopen({outdir, "/epochs.csv"}, "w");
        summary_file = $fopen({outdir, "/summary.json"}, "w");
        if (!trace_file || !event_file || !epoch_file || !summary_file) $fatal(1, "Cannot open evidence");
        $fdisplay(trace_file, "cycle,phase,epoch,resetn,in_valid,in_ready,in_data_hex,in_keep,in_last,out_valid,out_ready,out_data_hex,out_keep,out_last,push,pop,pending_before,pending_after,accepted_total,output_total,reset_discarded_total,peak,source_stall_cycles,first_offer_cycle");
        $fdisplay(event_file, "accepted_id,epoch,data_hex,first_offer_cycle,input_accept_cycle,output_accept_cycle,reset_cycle,event,source_wait_cycles,fifo_residence_cycles,offer_to_output_cycles");
        $fdisplay(epoch_file, "epoch,end_reason,end_cycle,accepted,output,reset_discarded,pending,peak,source_stall_cycles,unaccepted_offer_reset_aborts");
        drive("startup_reset", 0, 0, 0, 3);
        flow();
        drive("fill_before_reset", 1, 1, 0, DEPTH + 8);
        drive("reset_buffered", 0, 0, 0, 3);
        flow();
        drive("final_drain", 1, 0, 1, DEPTH + 8);
        @(negedge clk);
        if (beats.size() != 0 || discarded != DEPTH || peak != DEPTH || emitted == 0 || source_stalls == 0)
            $fatal(1, "Incomplete measurement scenario");
        if (epoch_input != epoch_output) $fatal(1, "Final epoch did not drain");
        $fdisplay(epoch_file, "%0d,drained,%0d,%0d,%0d,0,0,%0d,%0d,0",
                  epoch, cycle, epoch_input, epoch_output, epoch_peak, epoch_stalls);
        $fdisplay(summary_file,
            "{\"result\":\"PASS\",\"depth\":%0d,\"backpressure\":%0d,\"clock_period_ns\":10,\"cycles\":%0d,\"accepted\":%0d,\"output\":%0d,\"reset_discarded\":%0d,\"pending\":%0d,\"peak\":%0d,\"source_stall_cycles\":%0d,\"latency_samples\":%0d,\"latency_sum_cycles\":%0d,\"latency_min_cycles\":%0d,\"latency_max_cycles\":%0d}",
            DEPTH, BACKPRESSURE, cycle, accepted, emitted, discarded, beats.size(), peak,
            source_stalls, emitted, latency_sum, latency_min, latency_max);
        $display("PASS depth=%0d backpressure=%0d in=%0d out=%0d reset_discard=%0d pending=%0d peak=%0d latency=%0d..%0d clocks",
                 DEPTH, BACKPRESSURE, accepted, emitted, discarded, beats.size(), peak, latency_min, latency_max);
        $fclose(trace_file);
        $fclose(event_file);
        $fclose(epoch_file);
        $fclose(summary_file);
        $finish;
    end
    initial begin
        #10000;
        $fatal(1, "Finite measurement timeout");
    end
endmodule
`default_nettype wire
