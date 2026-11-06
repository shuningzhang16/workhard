# P1 理想固定占空比 Buck：LTspice 实际结果

LTspice 26.1.1 已完成稳态和零初态启动仿真，两项进程均退出 0，原来的 **8 项判据全部通过**。稳态已与同参数 Python 开关模型、ngspice 结果对照。本目录记录理想开环电路仿真，不是器件模型、闭环控制、保护、效率或板端实测。

模型参数：Vin=9 V，D=2/9，50 kHz，L=220 µH，C=470 µF，R=4 Ω；LTspice 电感显式 Rser=0。LTspice/ngspice 使用 1 ns 有限边沿并补偿脉冲面积，Python 参考使用瞬时边沿。

## 最终结果

稳态保存窗口为 59.6–60 ms。均值使用不等间隔采样的时间加权梯形积分，峰峰值取窗口内最大值减最小值；不是直接对采样点做算术平均。

| 指标 | LTspice | Python | ngspice |
| --- | ---: | ---: | ---: |
| Vout 均值 / V | 2.000000415 | 2.000000230 | 2.000000230 |
| IL 均值 / A | 0.500000485 | 0.500000076 | 0.500000093 |
| Vout 峰峰值 / mV | 0.752595292 | 0.752197878 | 0.751887738 |
| IL 峰峰值 / mA | 141.413854 | 141.422437 | 141.414888 |

完整数值见 [comparison.csv](successful_run/comparison.csv) 和 [summary.json](summary.json)。LTspice 与 ngspice 的 Vout 纹波差约 0.0941%，IL 纹波差约 -0.000732%；有限边沿与采样间隔也会影响与 Python 的纹波差异。

| 原判据 | 实际结果 |
| --- | --- |
| DC 电压误差 < 10 µV | 0.4151 µV，通过 |
| DC 电流误差 < 10 µA | 0.4849 µA，通过 |
| Vout 纹波相对理想公式误差 < 2% | 通过 |
| IL 纹波相对理想公式误差 < 2% | 通过 |
| 启动首个保存时刻在 0–1 ns | 0 s，通过 |
| 启动首点 abs(Vout) < 1 µV | 0 V，通过 |
| 启动首点 abs(IL) < 1 µA | 0 A，通过 |
| 两项 LTspice 数据均有限 | 通过 |

稳态 RAW 保存 8324 点；启动覆盖 0–200 µs，保存 4244 点。完整命令、退出状态、CIR、LOG、ASCII RAW、解析 CSV 与两套参考 CSV 均在 [successful_run](successful_run/) 中。该目录逐字节保留本次成功运行，包括原始 summary；顶层 summary 只补全数值求解设置的说明，指标与判据没有变化。

## 失败与修复过程

- [带 -run 的最小探针](probes/with_run/summary.json)：已生成 LOG/RAW，30 秒后进程仍未退出，被限时终止。它是批处理退出行为问题，不能描述为没有完成求解。[仅 -b -ascii 的探针](probes/batch_only/summary.json) 正常退出 0；后续 Buck 使用后者，不覆盖用户 INI。
- [v1 执行错误](attempts/v1_v2/execution_stderr.txt)：两项 Buck 求解成功后，Python 参考在 PWM 边沿保留的重复时间戳触发了分析程序的“严格递增”要求。v2 保留样本，零宽区间积分贡献为零，并继续拒绝倒序时间；[临时对照](attempts/v1_v2/run/analysis_v2/summary.json) 显示 7/8 通过，DC 电流误差约 15.891 µA 仍超出原 10 µA 限值。
- 旧稳态 RAW 的 Offset=0.0596 s，旧 CSV/analysis_v2 未加 Offset，把窗口标为相对 0–0.4 ms。最终解析恢复绝对 59.6–60 ms。原始 RAW/旧 CSV/旧摘要均保留；常量平移不改变此前四项均值或峰峰值。
- [v3](attempts/v3/run/summary.json) 只收紧 reltol=1e-7、abstol=1e-10、vntol=1e-9，并修正 Offset，DC 电流误差仍约 15.891 µA，检查保持失败。
- v4 在相同容差下把稳态最大步长从 0.25 µs 降到 0.05 µs，DC 电流误差降到 0.4849 µA；启动最大步长本来就是 0.05 µs。L/C/R/Vin/占空比/频率/边沿及全部验收阈值保持不变，没有用放宽阈值获得通过。

原始 CIR 中“LTspice has not been run”是从旧源网表保留的历史注释；本次状态以对应 run.json 和 LTspice 生成的 .log 为准。

## 复现与证据

[run_buck_batch_v4.py](run_buck_batch_v4.py) 保留实际执行计算，仅补全 summary 的说明字符串；[原执行版本](execution/run_buck_batch_v4_executed.py) 和 [执行输出](execution/v4_stdout.txt) 另存。脚本使用本机完整路径，复现前核对 REPO、SIM、EXE 和输出根位置；当前机器可执行：

~~~powershell
& 'E:\python.exe' -B .\run_buck_batch_v4.py
~~~

每次创建新的 E:/codex_ltspice_runs/buck_时间戳 目录，保留命令、失败和成功产物。脚本会调用已安装 LTspice，本次归档过程本身没有重跑仿真。它读取同仓库原有 Python/ngspice 参考 CSV。

[source_files.csv](source_files.csv) 记录归档原文件的来源和字节数；所有原文件复制后逐字节核对，未复制程序、用户 INI 或凭据。v1/v2/v3 仅选取定位本次失败所需的记录；完整成功运行和两个最小探针均保留。

本页汇总稳态/启动；[后续实际负载阶跃三方对照](../load_step_spice_20261106/README.md)已完成，原 9 项检查通过，开环恢复约 3.769 ms。闭环、保护、器件非理想因素和硬件验证不由这些开环结果证明。
