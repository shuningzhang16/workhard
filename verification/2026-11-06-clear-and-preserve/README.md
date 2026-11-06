# 2026-11-06 清除条件及证据保留验证

P1 量化路径改用完整 ADC 码箱上界，信息不足时保持故障锁存；P4 SPICE 运行器保留旧文件，使用新的输出目录。没有删除文件或执行硬件操作。

- [P1 三项统一检查](p1/summary.json)：Python 16 项、原主机 C 回放、实际 C 闭环均成功；完整控制修复及目标编译见 [P1 报告](../../experiments/p1-c2000-buck/host_c/CLEAR_MEASUREMENTS.md)。
- [P1 独立码箱审查](p1-peer-review/README.md)：分别扫描全部电压码和全部电流码，共 8192 项；这不是 4096² 组合检查，未执行目标 ISR。
- [P4 自动发现测试](p4/p4_dab.log)：55 项通过。
- [SPICE 隔离定向测试](spice-isolated-tests.log)：已有数据/日志保留且不调用进程；新目录退出零但无数据仍拒绝；不完整/非有限轨迹仍拒绝。
- [六个真实 ngspice 电路](spice-actual-run.log)：实际运行全部成功；[数值汇总](spice-summary.csv) 最大节点差约 1.190 mV，最大电流差约 6.572 µA，原比较容差不变。

全量本机输出保留在根 `.runs/20261106-103049-802933`、`.runs/20261106-103213-971749` 及 `.runs/spice-preserve-actual-20261106-103340-655998`。SPICE 原始数据未被旧结果替代。本记录不证明 PLECS、LTspice、Vivado/BSP 或板端运行已完成。
