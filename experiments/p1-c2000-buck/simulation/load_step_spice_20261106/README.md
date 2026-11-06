# Buck 固定占空比负载阶跃：三方实际对照

LTspice 26.1.1、ngspice 36 和独立 Python 开关模型均已实际运行。固定 9 V、D=2/9、50 kHz、L=220 µH、C=470 µF，初始电压/电流为零；50 ms 时负载从 4 Ω 变为 2 Ω。新增并联支路由 BSTEP 表示，L/C 状态不重置。这是开环电路验证，原有 C/Python 闭环与保护结果另行记录。

| 指标 | LTspice | ngspice | Python |
| --- | ---: | ---: | ---: |
| 阶跃后最低输出 / V | 1.731265667 | 1.731267388 | 1.731265588 |
| 随后最高输出 / V | 2.155769814 | 2.155771264 | 2.155769837 |
| 恢复至 ±2% / ms | 3.769223 | 3.769023 | 3.769383 |
| 末稳态输出均值 / V | 2.000000404 | 2.000000000 | 2.000000000 |
| 末稳态电流均值 / A | 1.000000970 | 1.000000000 | 1.000000000 |

LTspice 前后稳态 DC 10 µV/10 µA、纹波相对公式 2% 及有限数据共 9 项检查全部通过；ngspice 对照同样 9 项通过。没有放宽既有 DC/纹波限值，也没有为开环恢复时间新增闭环判据。详见[完整三方统计](analysis_01/summary.json)、[指标表](analysis_01/comparison.csv)和[ngspice 独立检查](ngspice_reference/summary.json)。

LTspice 与 Python 在声明的阶跃比较窗口内最大电压差 1.074 µV、电流差 16.803 µA；与 ngspice 最大差 0.121526 mV/0.139396 mA。这些是实际差值，不是另设的通过门槛。两种 SPICE 沿用 1 ns 面积补偿 PWM 边沿，Python 使用理想瞬时边沿。

## 窗口、完整性与数值设置

- LTspice 两次独立零初态积分分别到 60 ms 和 100 ms，均正常退出 0。前者保存 49.6–60 ms 共 216244 点，后者保存 99.6–100 ms 共 8323 点。
- 恢复时间只根据 50–60 ms 记录：最后一个带外点之后首次进入 ±2%，保持至 60 ms 且至少有 2 ms 观察余量。没有声称 60–100 ms 全程均在带内；末稳态来自第二次积分。
- 比较前稳态统一使用 49.62–50 ms 的 19 个完整周期，末稳态使用 99.6–100 ms 的共同记录范围。只在已有数据内插值端点，不外推。
- LTspice 最大步长 50 ns，reltol=1e-7、abstol=1e-10、vntol=1e-9；ngspice/Python 最大步长 250 ns。LTspice 的 RAW Offset 已恢复成绝对时间。
- Git 中有限 CSV 只包含 49.8–50.6 ms 和 99.98–100 ms 的实际保存点，未平滑。完整 LTspice RAW/CSV、ngspice DAT 和 Python 参考保留在 summary 指向的本地新目录；不是把有限片段标成全程数据。

首次 ngspice 分析试图访问第一个保存点之前的 49.6 ms，报告 `Requested point precedes saved waveform`；实际求解已成功。随后在新分析目录使用完整的 49.62–50 ms 周期窗，没有重跑、外推或改阈值。`ngspice_reference/original_run_load_step.py` 是该阶段生成脚本归档，完整入口含此前的分析路径；复用它时使用 `--prepare-only` 生成新目录，然后独立执行网表与本目录分析程序。

## 源码和复现

- LTspice 实际网表和日志：[阶跃](analysis_01/step_step.cir)、[末稳态](analysis_01/post_post.cir)，对应 `step_run.json`、`post_run.json` 保存命令和退出状态。网表可复制到全新的目录，以已安装的 LTspice `-b -ascii` 运行。
- ngspice 实际网表：[buck_load_step_ngspice.cir](ngspice_reference/buck_load_step_ngspice.cir)。在新输出目录执行本机已解压的 ngspice，不能复用本目录输出文件。
- [compare_three.py](compare_three.py) 与 [analyze_existing.py](analyze_existing.py) 只读取已完成的数据，`--lt`、`--ng` 指向实际运行目录，`--output` 必须是不存在的新目录；不启动仿真或读取应用设置。
- [run_ltspice_load_step.py](analysis_01/run_ltspice_load_step.py) 保留实际执行源码，使用本机已记录的绝对路径和解析器；跨目录复现须调整路径。完整仿真并不依赖在 PLECS 或其他 GUI 中操作。

上述结果不证明器件损耗、效率、采样保护、目标 ISR 或硬件运行。此前的[启动/稳态 8 项检查](../ltspice_results_20261106/README.md)独立保留。
