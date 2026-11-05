`timescale 1ns / 1ps
`default_nettype none

module tb_daq_axi_lite;
    localparam integer FRAME_WORDS = 7;
    reg clk = 0, resetn = 0, stream_resetn = 1;
    always #5 clk = !clk;
    reg [5:0] awaddr = 0, araddr = 0;
    reg awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    reg [31:0] wdata = 0;
    reg [3:0] wstrb = 0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata, data;
    wire [3:0] keep;
    wire valid, last;
    reg ready = 0;
    integer cycle = 0, epoch_word = 0, metric_words = 0, metric_frames = 0, metric_stalls = 0;
    integer total_words = 0, total_frames = 0, total_stalls = 0;
    integer aw_count = 0, w_count = 0, b_count = 0, ar_count = 0, r_count = 0;
    integer b_stalls = 0, r_stalls = 0, aw_wait = 0, w_wait = 0, ar_wait = 0;
    integer aw_first = 0, w_first = 0, same_cycle = 0, aw_cycle = -1, w_cycle = -1;
    integer csv_file, bus_file, summary_file;
    reg held_stream = 0, held_b = 0, held_r = 0;
    reg [36:0] held_beat;
    reg [1:0] held_bresp, held_rresp;
    reg [31:0] held_rdata, expected_read;
    reg check_read = 0;
    integer words_before;
    string outdir;

    daq_axi_lite dut (
        .aclk(clk), .aresetn(resetn), .stream_resetn(stream_resetn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b000), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b000), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .m_axis_tdata(data), .m_axis_tkeep(keep), .m_axis_tvalid(valid),
        .m_axis_tready(ready), .m_axis_tlast(last)
    );

    // Reference uses only public interface handshakes, never DUT registers.
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (resetn) begin
            if (held_stream && stream_resetn && (!valid || {last, keep, data} !== held_beat))
                $fatal(1, "Stream changed while stalled, cycle %0d", cycle);
            if (held_b && (!bvalid || bresp !== held_bresp)) $fatal(1, "B response not held");
            if (held_r && (!rvalid || {rresp, rdata} !== {held_rresp, held_rdata}))
                $fatal(1, "R response not held");
            if (bvalid && (aw_count <= b_count || w_count <= b_count))
                $fatal(1, "B response before both AW and W");
            if (bvalid && (awready || wready)) $fatal(1, "Accepted write over held response");
            if (rvalid && arready) $fatal(1, "Accepted read over held response");
            if (bvalid && bready) begin
                b_count++;
                if (aw_cycle < w_cycle) aw_first++;
                else if (w_cycle < aw_cycle) w_first++;
                else same_cycle++;
                $fdisplay(bus_file, "%0d,B,0,%08x,0", cycle, {30'd0, bresp});
            end
            if (rvalid && rready) begin
                r_count++;
                if (check_read && (rresp !== 0 || rdata !== expected_read))
                    $fatal(1, "Counter snapshot mismatch got %0d expected %0d", rdata, expected_read);
                $fdisplay(bus_file, "%0d,R,0,%08x,%0d", cycle, rdata, rresp);
            end
            if (awvalid && awready) begin
                aw_count++;
                aw_cycle = cycle;
                $fdisplay(bus_file, "%0d,AW,%02x,0,0", cycle, awaddr);
            end
            if (wvalid && wready) begin
                w_count++;
                w_cycle = cycle;
                $fdisplay(bus_file, "%0d,W,0,%08x,%x", cycle, wdata, wstrb);
            end
            if (arvalid && arready) begin
                ar_count++;
                check_read = 1;
                case (araddr)
                    6'h0c: expected_read = metric_words;
                    6'h10: expected_read = metric_frames;
                    6'h14: expected_read = metric_stalls;
                    default: check_read = 0;
                endcase
                $fdisplay(bus_file, "%0d,AR,%02x,0,0", cycle, araddr);
            end
            if (bvalid && !bready) b_stalls++;
            if (rvalid && !rready) r_stalls++;
            if (awvalid && !awready) aw_wait++;
            if (wvalid && !wready) w_wait++;
            if (arvalid && !arready) ar_wait++;
            if (valid && ready) begin
                if (data !== (((epoch_word / FRAME_WORDS) << 16) | (epoch_word % FRAME_WORDS)) ||
                    keep !== 4'hf || last !== (epoch_word % FRAME_WORDS == FRAME_WORDS - 1))
                    $fatal(1, "Output sequence mismatch at epoch word %0d", epoch_word);
                epoch_word++;
                metric_words++;
                total_words++;
                if (last) begin metric_frames++; total_frames++; end
            end
            if (valid && !ready) begin metric_stalls++; total_stalls++; end
            $fdisplay(csv_file, "%0d,%0d,%0d,%08x,%x,%0d,%0d,%0d,%0d,%0d", cycle,
                      valid, ready, data, keep, last, epoch_word, metric_words, metric_frames, metric_stalls);
        end
        held_stream = resetn && stream_resetn && valid && !ready;
        held_b = resetn && bvalid && !bready;
        held_r = resetn && rvalid && !rready;
        held_beat = {last, keep, data};
        held_bresp = bresp;
        held_rresp = rresp;
        held_rdata = rdata;
    end

    task automatic send_aw(input [5:0] address, input integer delay_cycles);
        @(negedge clk);
        repeat (delay_cycles) @(negedge clk);
        awaddr = address; awvalid = 1;
        do @(posedge clk); while (!awready);
        @(negedge clk); awvalid = 0;
    endtask
    task automatic send_w(input [31:0] value, input [3:0] strobe, input integer delay_cycles);
        @(negedge clk);
        repeat (delay_cycles) @(negedge clk);
        wdata = value; wstrb = strobe; wvalid = 1;
        do @(posedge clk); while (!wready);
        @(negedge clk); wvalid = 0;
    endtask
    task automatic collect_b(input integer hold_cycles, input [1:0] response);
        @(negedge clk);
        while (!bvalid) @(negedge clk);
        if (bresp !== response) $fatal(1, "Unexpected BRESP %0d expected %0d", bresp, response);
        repeat (hold_cycles) @(negedge clk);
        bready = 1;
        @(negedge clk); bready = 0;
    endtask
    task automatic write_reg(input [5:0] address, input [31:0] value, input [3:0] strobe,
                             input integer aw_delay, input integer w_delay,
                             input integer hold_cycles, input [1:0] response);
        fork
            send_aw(address, aw_delay);
            send_w(value, strobe, w_delay);
        join
        collect_b(hold_cycles, response);
    endtask
    task automatic send_ar(input [5:0] address);
        @(negedge clk); araddr = address; arvalid = 1;
        do @(posedge clk); while (!arready);
        @(negedge clk); arvalid = 0;
    endtask
    task automatic collect_r(input integer hold_cycles, input [1:0] response,
                             input bit check_value, input [31:0] value);
        @(negedge clk);
        while (!rvalid) @(negedge clk);
        if (rresp !== response || (check_value && rdata !== value))
            $fatal(1, "Unexpected read data/response: %08x/%0d expected %08x/%0d", rdata, rresp, value, response);
        repeat (hold_cycles) @(negedge clk);
        rready = 1;
        @(negedge clk); rready = 0;
    endtask
    task automatic read_reg(input [5:0] address, input integer hold_cycles,
                            input [1:0] response, input bit check_value, input [31:0] value);
        send_ar(address);
        collect_r(hold_cycles, response, check_value, value);
    endtask
    task automatic check_counts;
        read_reg(6'h0c, 3, 0, 0, 0);
        read_reg(6'h10, 2, 0, 0, 0);
        read_reg(6'h14, 4, 0, 0, 0);
    endtask
    task automatic reset_metrics;
        metric_words = 0; metric_frames = 0; metric_stalls = 0;
    endtask
    task automatic drain_stop;
        @(negedge clk); ready = 1;
        while (valid) @(negedge clk);
        if (epoch_word % FRAME_WORDS != 0) $fatal(1, "STOP split a frame");
        words_before = total_words;
        repeat (4) @(negedge clk);
        if (valid || total_words != words_before) $fatal(1, "Output after STOP boundary");
        read_reg(6'h04, 2, 0, 1, 0);
    endtask

    initial begin
        if (!$value$plusargs("OUTDIR=%s", outdir)) outdir = ".";
        csv_file = $fopen({outdir, "/stream_cycles.csv"}, "w");
        bus_file = $fopen({outdir, "/axi_transactions.csv"}, "w");
        if (!csv_file || !bus_file) $fatal(1, "Cannot open traces");
        $fdisplay(csv_file, "cycle,valid,ready,data_hex,keep_hex,last,epoch_words,metric_words,metric_frames,metric_stalls");
        $fdisplay(bus_file, "cycle,channel,address_hex,data_hex,strobe_or_response");
        repeat (3) @(negedge clk);
        resetn = 1;
        read_reg(0, 0, 0, 1, 0);
        read_reg(4, 0, 0, 1, 0);
        check_counts();

        // AW before W, W before AW, and ignored byte lanes / zero strobes.
        write_reg(0, 1, 0, 0, 4, 2, 0);
        write_reg(0, 1, 8, 4, 0, 2, 0);
        read_reg(4, 0, 0, 1, 0);
        // Offer the next write while B is stalled; payload must wait intact.
        fork send_aw(0, 0); send_w(1, 0, 0); join
        fork collect_b(6, 0); send_aw(0, 0); send_w(1, 2, 0); join
        collect_b(2, 0);
        // Same exercise for AR while a prior R response is stalled.
        send_ar(6'h0c);
        fork collect_r(6, 0, 1, 0); send_ar(6'h14); join
        collect_r(2, 0, 1, 0);

        // Invalid/unaligned and read-only accesses do not change acquisition.
        write_reg(6'h0c, 123, 15, 0, 0, 1, 2);
        write_reg(6'h3c, 1, 15, 0, 2, 1, 2);
        read_reg(6'h01, 2, 2, 1, 0);
        read_reg(6'h3c, 2, 2, 1, 0);
        write_reg(0, 32'hffffff01, 1, 0, 4, 5, 0);
        if (!valid || data !== 0) $fatal(1, "START did not expose first word");
        read_reg(4, 2, 0, 1, 1);
        check_counts(); // Stall counter changes while its read response is held.
        write_reg(8, 3, 0, 0, 0, 2, 0); // Masked command is inert, even running.
        write_reg(8, 3, 1, 0, 0, 2, 2); // Active restart/clear must be rejected.
        write_reg(0, 0, 1, 4, 0, 3, 0);
        read_reg(4, 1, 0, 1, 3);
        read_reg(0, 1, 0, 1, 0);
        if (!valid || data !== 0) $fatal(1, "STOP withdrew a held first beat");
        drain_stop();
        if (epoch_word != 7) $fatal(1, "First stop did not finish exactly one frame");
        check_counts();

        // Clearing metrics must preserve the next prefetched frame sequence.
        write_reg(8, 2, 2, 0, 0, 1, 0);
        check_counts();
        write_reg(8, 2, 1, 0, 2, 1, 0);
        reset_metrics();
        check_counts();
        write_reg(0, 1, 15, 0, 0, 0, 0);
        fork
            begin
                repeat (6) write_reg(0, 1, 1, 0, 0, 0, 0);
            end
            begin
                repeat (4) begin
                    read_reg(6'h0c, 3, 0, 0, 0);
                    read_reg(6'h10, 2, 0, 0, 0);
                end
            end
        join
        // Hold TLAST, request stop, and release exactly that beat.
        @(negedge clk);
        while (!(valid && last)) @(negedge clk);
        ready = 0;
        words_before = total_words;
        write_reg(0, 0, 1, 0, 3, 3, 0);
        read_reg(4, 1, 0, 1, 3);
        if (!valid || !last || total_words != words_before) $fatal(1, "Held TLAST lost");
        drain_stop();
        check_counts();

        // Explicit restart discards prefetched data and starts a new epoch at 0.
        write_reg(8, 1, 1, 3, 0, 2, 0);
        epoch_word = 0;
        reset_metrics();
        check_counts();
        @(negedge clk); ready = 0;
        write_reg(0, 1, 1, 0, 0, 0, 0);
        if (!valid || data !== 0) $fatal(1, "Restart did not return to frame zero");
        write_reg(0, 0, 1, 0, 0, 0, 0);
        drain_stop();
        if (epoch_word != 7) $fatal(1, "Restart epoch did not complete one frame");
        check_counts();
        // A DMA stream reset must not cancel an outstanding AXI-Lite response.
        send_ar(6'h04);
        fork
            collect_r(6, 0, 1, 0);
            begin
                @(negedge clk); stream_resetn = 0;
                repeat (3) @(negedge clk);
                epoch_word = 0; reset_metrics();
            end
        join
        read_reg(6'h04, 1, 0, 1, 4);
        write_reg(0, 1, 1, 0, 0, 1, 2); // START rejected until DMA reset releases.
        check_counts();
        @(negedge clk); stream_resetn = 1; ready = 0;
        write_reg(0, 1, 1, 0, 0, 0, 0);
        if (!valid || data !== 0) $fatal(1, "DMA stream reset did not reset sequence");
        write_reg(0, 0, 1, 0, 0, 0, 0);
        drain_stop();
        if (epoch_word != 7) $fatal(1, "Post-DMA-reset frame incomplete");
        check_counts();
        if (aw_count != w_count || w_count != b_count || ar_count != r_count ||
            !aw_first || !w_first || !same_cycle || !b_stalls || !r_stalls ||
            !aw_wait || !w_wait || !ar_wait)
            $fatal(1, "Missing transaction/ordering/backpressure coverage");
        summary_file = $fopen({outdir, "/summary.json"}, "w");
        $fdisplay(summary_file, "{\"result\":\"PASS\",\"cycles\":%0d,\"words\":%0d,\"frames\":%0d,\"stream_stalls\":%0d,\"writes\":%0d,\"reads\":%0d,\"aw_first\":%0d,\"w_first\":%0d,\"same_cycle\":%0d,\"b_stalls\":%0d,\"r_stalls\":%0d,\"aw_wait\":%0d,\"w_wait\":%0d,\"ar_wait\":%0d}",
                  cycle, total_words, total_frames, total_stalls, b_count, r_count,
                  aw_first, w_first, same_cycle, b_stalls, r_stalls, aw_wait, w_wait, ar_wait);
        $fclose(summary_file); $fclose(csv_file); $fclose(bus_file);
        $display("PASS AXI-Lite wrapper: %0d writes, %0d reads, %0d words, %0d frames; AW-first=%0d W-first=%0d simultaneous=%0d",
                 b_count, r_count, total_words, total_frames, aw_first, w_first, same_cycle);
        $finish;
    end
    initial begin
        #200000;
        $fatal(1, "Testbench timeout");
    end
endmodule

`default_nettype wire
