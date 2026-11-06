# 清除条件修复：用完整测量区间，信息不足时保持锁存

2026-11-06，针对 [上一阶段两类反例](CLOSED_LOOP.md) 完成最小修复：量化路径不再仅凭解码点值判断能否清除，而是提交可观测标记及完整码箱的电压/电流绝对值上界。PI、软启动、Trip 条件和原 `0.1 V / 0.1 A` 清除界限不变；目标 GPIO 输入、启动禁止输出与硬件 OST 永久锁存也不变。

**零码无法区分真实零电压与被截断的负电压。因此本次三个故障场景在 80 ms 收到显式请求后仍锁存，没有宣称完成硬件安全恢复。** 需要真实前端范围、标度及误差证据才能决定如何提供有效测量，增加固定等待不能补回丢失的信息。

## 最小接口与判定顺序

[`BuckClearEvidence`](buck_control.h) 只有 `observable`、`max_abs_output_v`、`max_abs_current_a` 三个字段。ADC/ctypes/目标 ISR 使用 [`buck_controller_step_observed`](buck_control.c)：

1. 活动故障仍优先拒绝清除；原解码点值超过清除界限也仍拒绝。
2. 缺失证据、不可观测、非有限界限或界限小于解码点的绝对值，返回 `rejected_unobservable_measurement`（枚举 5），状态和故障原因保持锁存。
3. 任一完整区间上界超过原 `0.1 V / 0.1 A`，返回原 `rejected_residual_energy`。
4. 只有明确请求、无活动故障且整个有效区间在原界内，才清除并从当前拍重新软启动。没有自动重启或等待后放行。

原标量 `buck_controller_step` 仅保留为历史**理想精确测量**回放入口。它不适用于 ADC，目标 ISR 和量化闭环均不调用它。Python 的未量化旧模型同样保留；量化运行总是显式传入码箱证据。真实功率级状态只用于积分和事后诊断，不能形成 C 的清除证据。原副本探测也不回写主轨迹。

[`adc_scaling.h`](../firmware/adc_scaling.h) 与 [`adc_clear_evidence`](../simulation/io_timing_buck.py) 都仅使用原码和现有标度。在声明的理想向下取整 ADC 模型下，内码 q 的输入区间为 `[q·LSB, (q+1)·LSB]`，保守地包含右端点。电流先扣除零点、除以增益，再取两端绝对值的较大者。Vout 或电流的 0、4095 端点码同时可能表示截断，均标为不可观测；不可观测时记录的名义码箱数值不是有效物理上界。

这些仍是教学标度及理想码箱，不包含实测偏置、噪声、增益误差、ADC 非线性或通道时间偏移。接口允许测量层提供包含已知误差的更宽界限，但本次没有虚构硬件误差预算，也没有增加负压传感器模型。

## 两类旧反例与有效内码

| 输入证据 | 解码或完整区间 | 当前 C 结果 |
| --- | --- | --- |
| 负压反例的 Vout=0、电流=2048 码 | 解码 0 V / 0 A；负电压不可辨识 | `rejected_unobservable_measurement` |
| 电流=2060 码，Vout=19 码 | 电流解码 0.0966796875 A，上界 0.104736328125 A | `rejected_residual_energy` |
| Vout=62、电流=2048 码 | 电压解码约 0.099902 V，上界约 0.101514 V | 拒绝，完整码箱超界 |
| Vout=1、电流=2048 码 | 电压上界 0.00322265625 V，电流上界约 0.00805664 A | 有显式请求时接受 |
| Vout=61、电流=2059 码 | 电压上界约 0.099902 V，电流上界约 0.0966797 A | 有显式请求时接受 |
| Vout=19、电流=2036 码 | 覆盖负电流的完整区间仍在 ±0.1 A 内 | 有显式请求时接受 |

负压反例的真实状态约为 −1.906609 V / 0.005453 A；电流反例约为 0.031066 V / 0.104541 A。这些真值只说明为什么旧判断不成立，不传入修复后的 C 判定。测试还让同一零码在第 1、4,000、50,000,000 拍请求清除，始终拒绝；有效内码没有请求时也保持锁存。

## 实际验证

- GCC 11.4 严格警告和 UBSan：原 C 边界测试、[`test_clear_measurements.c`](test_clear_measurements.c) 均通过。后者在主机真正执行 `p1_scale_adc` 和 observed C 入口，覆盖旧反例、正负内码、缺失/无效证据、完整码箱边界及显式请求。见 [原生命令与输出](clear_measurement_results/commands.json)。
- 六场景两种独立闭环再次执行：C 主轨迹 **36,006 次**调用，C/Python 的 duty、reference、vO、iL 最大差均为零，码箱、离散状态与事件一致；原正常性能和实际脉冲/续流检查通过。见 [状态汇总](clear_measurement_results/status.json)、[实现对照](clear_measurement_results/comparisons.json)。
- 三类故障在 80 ms 的 Vout 都为 0 码，显式清除均拒绝并保持锁存到记录结束。负压副本探测改为拒绝不可观测，电流量化副本探测改为拒绝残余状态。见 [请求记录](clear_measurement_results/clear_requests.csv)、[完整指标](clear_measurement_results/metrics.json)。这项行为改变是新增信息要求，不是把原“80 ms 已恢复”检查放宽。
- Python **16/16** 测试通过，包含原控制/功率级测试和新增三个有限测量测试；四周期 C 接管试验仍 **7/7**。见 [测试日志](clear_measurement_results/python_tests.log)、[接管结果](clear_measurement_results/takeover.json)。
- 历史理想标量入口另经 ASan/UBSan 实际回放 **26,004 点**，保持原零差结果，见 [本轮回放指标](clear_measurement_results/ideal_replay/metrics.json)；它只证明旧理想模型语义保留，不作为 ADC 清除修复证据。
- 修复后的 C 核心和目标 ISR 接口经 TI cl2000 25.11.1 实际重新编译链接：C28x ELF **70,428 字节**、RAM **4,728 个 16 位字**、Flash 0，14 个编译常量零差。见 [构建汇总](clear_measurement_results/target/build_summary.json)、[数值与内存](clear_measurement_results/target/numeric_and_image_summary.json)。镜像未执行，未连接或烧录硬件，未验证 ISR 耗时。

本轮 C ADC 换算函数的**主机定向执行**与目标 ADC 寄存器/ISR 的执行是两回事；后者仍未发生。闭环的量化和码箱生成仍由 Python 执行，C 控制核心依据传入证据作出决定。

## 复现及证据保留

从 P1 目录运行下面入口，默认自动选择全新目录；指定 `--output` 时也必须不存在。每次构建在该输出目录自己的 `build/` 内，不能复用旧结果或旧库。

```powershell
& 'E:\python.exe' -B -X utf8 .\host_c\run_closed_loop.py
& 'E:\python.exe' -B -X utf8 -m unittest discover -s .\simulation -p 'test_*.py' -v
& 'E:\python.exe' -B -X utf8 .\host_c\run_validation.py
& 'E:\python.exe' -B -X utf8 .\firmware\build_target.py
```

Linux 主机闭环入口是 `python3 -B host_c/run_closed_loop.py`。目标构建仍要求已有本地 TI 工具，不负责安装、连接或烧录。

完整新轨迹、编译对象、目标镜像、修改前源码均保存在本机新的 `.runs/p1-clear-measurement-20261106-003154/`；本页提交紧凑指标、明确请求、全部命令及目标元数据，位置说明见 [保留记录](clear_measurement_results/retained_paths.json)。既有 `closed_loop_results`、目标构建及历史失败证据均未删除或覆盖。历史报告中的 80 ms 恢复描述保留为旧标量判据的结果，不能代表当前量化入口。
