# 已运行结果与证据入口

以下均为离线仿真或主机验证，参数与适用范围以各实验说明为准。

| 工作 | 已取得的结果 | 证据 |
| --- | --- | --- |
| Buck 平均模型 | 默认 PI 下启动、负载与输入阶跃满足原响应检查；负载恢复 5.12 ms | [原始 CSV](../experiments/p1-c2000-buck/simulation/results/)、[测试](../experiments/p1-c2000-buck/simulation/test_buck.py) |
| Buck PI 比较 | 9 组增益中 3 组满足原条件；候选最差扰动偏差降低约 15%，最差恢复时间略增，默认值保留 | [参数比较](../experiments/p1-c2000-buck/simulation/PI_COMPARISON.md) |
| Buck 故障恢复 | 平均模型的过流、过压、欠压锁存和显式恢复；故障期间保留电感/电容状态 | [保护说明](../experiments/p1-c2000-buck/simulation/PROTECTION.md) |
| Buck PWM 开关 | 50 kHz、固定占空比稳态约 2 V；细步长纹波 0.752145 mV、0.141422 A；控制负载阶跃恢复 5.10 ms | [开关说明与数据](../experiments/p1-c2000-buck/simulation/SWITCHING.md) |
| Buck 独立 SPICE 对照 | ngspice 36 实际运行；8 项对照检查通过。整个稳态窗口的输出/电感纹波与 Python 分别相差约 −0.0412%/−0.00534% | [SPICE 报告](../experiments/p1-c2000-buck/simulation/SPICE_COMPARISON.md) |
| Buck PWM 保护 | 过流/过压/欠压分别在 50.32/50.30/50.00 ms 锁存；80 ms 显式清除后 30.50 ms 恢复；储能与反向振荡完整保留 | [保护报告](../experiments/p1-c2000-buck/simulation/PROTECTED_SWITCHING.md) |
| Buck 主机 C 控制 | 独立 C 实现按真实 PWM 采样输入逐拍运行，26,004 点与 Python 输出/状态一致；ASan/UBSan 与阈值边界检查通过 | [C 实现与证据](../experiments/p1-c2000-buck/host_c/) |
| C2000 目标构建 | TI cl2000 25.11.1.LTS 与官方 DriverLib 26.02 实际编译链接 F280049C RAM ELF；GPIO0/1 保持输入、PWM OST 持续强制关闭，未运行目标代码 | [目标工程与真实日志](../experiments/p1-c2000-buck/firmware/README.md) |
| Buck 延迟与量化 | 20 µs 命令延迟、12 位 ADC、2000 计数 PWM；负载恢复 5.10→5.18 ms，周期内峰值超调 10.0173%；找到负压被 ADC 截为零后的清除盲区 | [六工况、细步长和反例](../experiments/p1-c2000-buck/simulation/IO_TIMING.md) |
| AXI-Stream 数据源 | 帧长 1/7/16、背压稳定、复位及 16 位序号回绕 | [RTL 结果](../experiments/p2-zcu104-daq/results/first_step/summary.json) |
| 同步 FIFO | 深度 1/3/16、非 2 的幂指针回绕、满时同时读写、复位丢弃量均逐拍核对 | [FIFO 结果](../experiments/p2-zcu104-daq/results/fifo_step/summary.json) |
| 主机 C 帧校验 | 实际 RTL 的 12 帧、84 字、336 字节；16 项故障测试通过 ASan/UBSan | [结果汇总](../experiments/p2-zcu104-daq/results/frame_validator_repair/summary.json)、[故障矩阵](../experiments/p2-zcu104-daq/results/frame_validator_repair/fault_matrix.csv) |
| 顶层与 Vivado 入口 | source/FIFO 顶层实际经过 RTL→C 联测；ZCU104 Tcl 已提供，仅做文本完整性检查，未生成或验证真实块设计 | [工程入口及限制](../experiments/p2-zcu104-daq/vivado/README.md)、[顶层联测](../experiments/p2-zcu104-daq/results/top_integration/summary.json) |
| Simple S2MM 主机流程 | 13 项接收/错误/显式恢复用例通过 ASan/UBSan；真实 RTL 数据配合受控状态回调 | [接收与恢复](../experiments/p2-zcu104-daq/ps/simple_s2mm.md) |
| 通用综合后重放 | Yosys 实际综合，Icarus 原 RTL/网表的 84 个接收记录全部字段一致 | [综合记录](../verification/yosys-stream/README.md) |
| AXI-Lite 控制与综合 | 采集复位独立于控制总线；26 次写、55 次读，77 字/11 帧；综合网表与 RTL 的 546 个 stream 周期、188 条总线记录一致 | [寄存器说明](../experiments/p2-zcu104-daq/rtl/daq_axi_lite.md)、[最新网表重放](../verification/yosys-control/stream-reset/summary.json) |
| 采集启停会话 | 先提交 DMA 再 START，STOP 后有限排空，核对原定帧数；9 项主机测试通过，Tcl 已接入控制 wrapper 及地址导出入口 | [会话与目标工具限制](../experiments/p2-zcu104-daq/ps/daq_session.md) |
| 有界接收队列 | 容量 1/3/8 包、借用及释放、满队列背压和错误后保留有效前缀；13 项测试及 9 组主机测量通过 | [队列与实际测量](../experiments/p2-zcu104-daq/ps/daq_queue.md) |
| DAB SPS | 3 个电压比、39 个相移点；匹配电压 ±30° 时传输 ±20 W | [扫描与波形](../experiments/p4-dab/results/RESULTS.md) |
| DAB EPS 比较 | 同功率比较保留未改善和无解工况；电压比 0.75、±2.7 W 时 RMS 电流降低 31.183% | [EPS 结果](../experiments/p4-dab/results_eps/RESULTS.md) |
| DAB 瞬态与保护 | 四工况保留跨周期电流；换向、采样锁存、显式清除及能量收支通过 | [瞬态结果](../experiments/p4-dab/results_transient/RESULTS.md) |
| DAB 换流极性 | 40 个周期波形、320 个桥臂事件；电压比 0.75、±2.7 W 的所选 EPS 满足全部必要极性，仍不能确认 ZVS | [逐沿分析](../experiments/p4-dab/COMMUTATION.md) |
| DAB 功率 PI | 20→−15 W 在 4.150 ms 进入误差带；100 W 请求实际约 31.17 W，降回 10 W 后 3.750 ms 恢复 | [闭环结果](../experiments/p4-dab/POWER_LOOP.md) |
| DAB 固定增益五点验证 | 电压比/串联电阻五个指定点的 20 段目标均达本次误差带；最慢 5.000 ms，最高电流 1.498348 A | [参数与有限范围](../experiments/p4-dab/POWER_POINTS.md) |
| DAB 局部死区换流 | 线性 Coss、二极管钳位，24 个工况共 192 次开通；6 个独立 ngspice 窗口最大节点差 1.190 mV、电流差 6.572 µA | [局部求解及 SPICE 对照](../experiments/p4-dab/DEADTIME.md) |

## 可以复述的实际问题

Buck 首次 PI 参数未满足启动要求：保留原失败数据，在隔离副本调参后按相同条件重跑。后续参数扫描又表明降低最大偏差可能牺牲恢复速度，因此没有把一个候选称为全局最优。[首次失败记录](../experiments/p1-c2000-buck/evidence/simulation-attempt1/)

P2 首次主机联测在 WSL 路径转换处失败，而非 RTL 或 C 算法错误。直接执行模式保留 Windows 路径参数后，真实采集数据和 C 故障矩阵通过；失败日志与成功记录分别保存。[初始日志](../experiments/p2-zcu104-daq/results/frame_validator/runner_failure.log)

P2 队列测量的原终点在内容检查与释放之前，与文档定义不符。保存原源码及数据后，把终点移到成功释放之后，在隔离副本完成 9 组定向复测；当前报告只使用修复后的计时。[修复记录](../experiments/p2-zcu104-daq/ps/daq_queue.md)

DAB 过流清除后直接请求反向功率，导致再次锁存。保持 1.6 A 阈值，将恢复演示改为更慢的指令斜坡，并保留快速恢复再次跳闸的回归测试；不能通过增大阈值把这次失败隐藏掉。[定位记录](../experiments/p4-dab/diagnostics/transient_failure_01/README.md)

## 还不能据此宣称的内容

尚无 C2000 固件烧录、目标 ISR 测时或真实电源测量；真实目标编译没有证明引脚映射、量程和硬件 Trip 行为。尚无完整 Vivado 构建、ZCU104 器件时序、A53 BSP 编译、DMA 到 DDR 板端收数、cache 一致性或板端吞吐。DAB 采用独立教学参数，没有完整复现 Toshiba RD264，局部死区结果不能证明整机效率或实物 ZVS。

软件工具也有未完成项：Simulink 构建脚本尚无 MATLAB 运行结果；LTspice 已准备网表，但本机启动超时，未取得仿真结果。不能把剩余工作统称为“只差上板”。[工具实测记录](../verification/tooling/README.md)、[Simulink 入口](SIMULINK.md)
