# 固定背压下的 RTL 延迟与守恒测量

2026-11-05 使用现有 Icarus 实际编译并执行 [有限测量台](../tb/tb_fifo_latency.sv)，**6/6 组通过**。直接连接原 `axis_pattern_source` 与 `axis_sync_fifo`，深度为 1、3、16；未修改可综合 RTL、7 字帧格式、TKEEP=f 或 TLAST 判据。没有 DMA、DDR、不可停顿 ADC 或板端执行。

已有 [FIFO 测试](../results/fifo_step/summary.json) 已验证顺序、满交换、侧带稳定及复位守恒，保留不变。本次补充可复核的三个时间边界和全部有限轨迹，没有重复建立 FIFO 模型或读取 DUT 内部 `count`。

## 场景与边界

每组执行启动复位、64 个流动周期、关闭接收 `DEPTH+8` 个周期以填满、3 个复位周期、64 个流动周期，最后停止源输入并接收 `DEPTH+8` 个周期排空。若停止输入时已有被反压的字，先保持它到握手，避免非法撤回 VALID。

`b0` 在两个流动阶段始终 READY；`b1` 每固定 8 个周期的前 3 个 READY、后 5 个不 READY。所有组共有复位前的填满阶段，因此**全程峰值含该强制填满**，不能据 b0 的全程峰值推断连续接收需要深 FIFO。时钟周期设为 10 ns，仅是仿真激励，不代表实现后的时序收敛。

对每个字沿公开接口采样：

- `first_offer_cycle`：该字第一次在 FIFO 入口呈现 VALID 的上升沿；未握手时继续保持同一字。
- `input_accept_cycle`：入口 VALID && READY 的上升沿。
- `output_accept_cycle`：出口 VALID && READY 的上升沿。
- 源等待 = 入口握手 − 首次呈现；FIFO 驻留 = 出口握手 − 入口握手；首次呈现至输出 = 两者之和。均为时钟周期数，不是 ADC 采样到软件消费的端到端延迟。

独立 reference queue 只根据入口/出口握手更新，检查 payload、顺序及侧带；峰值从该队列推得。每周期核对 `已接受 = 已输出 + 复位丢弃 + 待输出`。复位丢弃的字没有输出延迟，不混入延迟均值；它们的首次呈现、入口和复位周期仍保留。复位前尚未握手的源字单列 `unaccepted_offer_reset_aborts`，不计入 FIFO 已接受量或其丢弃量。

## 实际结果

下表延迟均只统计最终输出的字，写为“均值 / 最大值”，单位为时钟；全量最小值、和及样本数见 [测量 CSV](../results/performance_fifo_boundaries/measurements.csv)。

| 深度 | 流动阶段接收 | 已接受 | 已输出 | 复位丢弃 | 最终待输出 | 全程峰值 | 源等待 | FIFO 驻留 | 首次呈现至输出 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 连续 | 126 | 125 | 1 | 0 | 1 | 0 / 0 | 1 / 1 | 1 / 1 |
| 3 | 连续 | 128 | 125 | 3 | 0 | 3 | 0 / 0 | 1 / 1 | 1 / 1 |
| 16 | 连续 | 141 | 125 | 16 | 0 | 16 | 0 / 0 | 1 / 1 | 1 / 1 |
| 1 | 固定 3/8 | 47 | 46 | 1 | 0 | 1 | 1.63 / 5 | 2.63 / 6 | 4.26 / 6 |
| 3 | 固定 3/8 | 51 | 48 | 3 | 0 | 3 | 1.38 / 5 | 7.35 / 8 | 8.73 / 13 |
| 16 | 固定 3/8 | 77 | 61 | 16 | 0 | 16 | 0.41 / 5 | 23.05 / 41 | 23.46 / 41 |

固定 3/8 的 epoch 0 在复位时分别为 `23=22+1+0`、`25=22+3+0`、`38=22+16+0`；每组另有 1 个尚未接受的源字被复位取消。epoch 1 则分别接受并完整输出 24、26、39 字，没有复位丢弃或最终待输出。更多输出包含最后排空的积压，不能把总字数差解释为固定接收窗口的持续吞吐提高。

本源可以暂停：VALID 被反压时内容保持且序号不前进。`source_stall_cycles` 是暂停周期，不是丢样数。不可停顿 ADC 在相同背压下是否丢样，需要 ADC 接口、采样时钟和溢出观测；本实验未模拟这些行为。此处只报告字数和时钟，不以历史测试中变化的 TKEEP=f/7/3/1 推算有效字节率。

## 证据与复现

[总汇总](../results/performance_fifo_boundaries/summary.json) 记录全部 6 组参数。每组 `cycles.csv` 保留所有 153、157 或 183 个周期；`beat_events.csv` 每个已接受字恰有一个 OUTPUT 或 RESET_DISCARD 结果；`epochs.csv` 单列各复位周期的计数与最终待处理量。原始接口在 reset 或 VALID=0 时的无效/x 字段不参与有效数据判断。

| 场景 | 完整周期 | 每字边界/去向 | 各 epoch | 编译/执行 |
| --- | --- | --- | --- | --- |
| 深度 1 连续 | [周期](../results/performance_fifo_boundaries/depth1_b0/cycles.csv) | [字](../results/performance_fifo_boundaries/depth1_b0/beat_events.csv) | [epoch](../results/performance_fifo_boundaries/depth1_b0/epochs.csv) | [编译](../results/performance_fifo_boundaries/depth1_b0/compile.log) / [执行](../results/performance_fifo_boundaries/depth1_b0/simulation.log) |
| 深度 1 固定背压 | [周期](../results/performance_fifo_boundaries/depth1_b1/cycles.csv) | [字](../results/performance_fifo_boundaries/depth1_b1/beat_events.csv) | [epoch](../results/performance_fifo_boundaries/depth1_b1/epochs.csv) | [编译](../results/performance_fifo_boundaries/depth1_b1/compile.log) / [执行](../results/performance_fifo_boundaries/depth1_b1/simulation.log) |
| 深度 3 连续 | [周期](../results/performance_fifo_boundaries/depth3_b0/cycles.csv) | [字](../results/performance_fifo_boundaries/depth3_b0/beat_events.csv) | [epoch](../results/performance_fifo_boundaries/depth3_b0/epochs.csv) | [编译](../results/performance_fifo_boundaries/depth3_b0/compile.log) / [执行](../results/performance_fifo_boundaries/depth3_b0/simulation.log) |
| 深度 3 固定背压 | [周期](../results/performance_fifo_boundaries/depth3_b1/cycles.csv) | [字](../results/performance_fifo_boundaries/depth3_b1/beat_events.csv) | [epoch](../results/performance_fifo_boundaries/depth3_b1/epochs.csv) | [编译](../results/performance_fifo_boundaries/depth3_b1/compile.log) / [执行](../results/performance_fifo_boundaries/depth3_b1/simulation.log) |
| 深度 16 连续 | [周期](../results/performance_fifo_boundaries/depth16_b0/cycles.csv) | [字](../results/performance_fifo_boundaries/depth16_b0/beat_events.csv) | [epoch](../results/performance_fifo_boundaries/depth16_b0/epochs.csv) | [编译](../results/performance_fifo_boundaries/depth16_b0/compile.log) / [执行](../results/performance_fifo_boundaries/depth16_b0/simulation.log) |
| 深度 16 固定背压 | [周期](../results/performance_fifo_boundaries/depth16_b1/cycles.csv) | [字](../results/performance_fifo_boundaries/depth16_b1/beat_events.csv) | [epoch](../results/performance_fifo_boundaries/depth16_b1/epochs.csv) | [编译](../results/performance_fifo_boundaries/depth16_b1/compile.log) / [执行](../results/performance_fifo_boundaries/depth16_b1/simulation.log) |

从实验根目录执行 [测量脚本](../scripts/run_fifo_latency.py)，新结果另选目录：

```powershell
& 'E:\python.exe' scripts/run_fifo_latency.py --output results/fifo_latency_recheck
```

脚本实际调用 Icarus，并用完整公开端口轨迹复核每字三个时间戳及每 epoch 守恒。此前只记录接受后驻留的 [首轮汇总](../results/performance_fifo/summary.json) 和所有旧结果均保留；当前报告使用补齐首次呈现边界后的结果。软件队列的 CPU/墙钟测量另见 [队列说明](../ps/daq_queue.md)，两种时钟不混合。
