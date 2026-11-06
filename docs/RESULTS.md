# 已运行结果与证据入口

以下均为离线仿真或主机验证，参数与适用范围以各实验说明为准。

| 工作 | 已取得的结果 | 证据 |
| --- | --- | --- |
| Buck 平均模型 | 默认 PI 下启动、负载与输入阶跃满足原响应检查；负载恢复 5.12 ms | [原始 CSV](../experiments/p1-c2000-buck/simulation/results/)、[测试](../experiments/p1-c2000-buck/simulation/test_buck.py) |
| Buck PI 比较 | 9 组增益中 3 组满足原条件；候选最差扰动偏差降低约 15%，最差恢复时间略增，默认值保留 | [参数比较](../experiments/p1-c2000-buck/simulation/PI_COMPARISON.md) |
| Buck 故障恢复 | 平均模型的过流、过压、欠压锁存和显式恢复；故障期间保留电感/电容状态 | [保护说明](../experiments/p1-c2000-buck/simulation/PROTECTION.md) |
| Buck PWM 开关 | 50 kHz、固定占空比稳态约 2 V；细步长纹波 0.752145 mV、0.141422 A；控制负载阶跃恢复 5.10 ms | [开关说明与数据](../experiments/p1-c2000-buck/simulation/SWITCHING.md) |
| Buck 独立 SPICE 对照 | ngspice 36 实际运行；8 项对照检查通过。整个稳态窗口的输出/电感纹波与 Python 分别相差约 −0.0412%/−0.00534% | [SPICE 报告](../experiments/p1-c2000-buck/simulation/SPICE_COMPARISON.md) |
| Buck PWM 保护（历史理想标量） | 过流/过压/欠压分别在 50.32/50.30/50.00 ms 锁存；旧判据在 80 ms 显式清除后 30.50 ms 恢复；不代表当前量化入口 | [历史保护报告](../experiments/p1-c2000-buck/simulation/PROTECTED_SWITCHING.md) |
| Buck 主机 C 理想回放 | 原精确标量测量入口回放 26,004 点，与 Python 输出/状态一致；本次修复后 ASan/UBSan 重跑仍零差，不能替代 ADC 区间验证 | [C 实现与证据](../experiments/p1-c2000-buck/host_c/) |
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
| DAB 连续整周期 | 跨死区、接轨与周期边界保留状态；16 工况各 100 周期均收敛，44 项测试通过；原理想相移不再保证相同实际功率 | [连续模型及功率误差](../experiments/p4-dab/CONTINUOUS.md) |
| DAB 实际接收功率与部分损耗 | 10 次尝试中 9 个匹配、1 个指定区间未匹配，误差≤8.15 µW；47 项测试及 9 份完整轨迹检查通过。13.5 W 时 EPS 的 RMS 略低，但典型部分损耗比 SPS 高约 0.0370 W | [匹配、分项预算和未建模项](../experiments/p4-dab/results_loss_budget/RESULTS.md) |
| Buck 实际 C 闭环与清除修复 | 修复后六场景共 36,006 次 C 调用，与独立 Python 闭环零差，短接管 7/7；16 项 Python 测试及 C ADC/码箱测试通过。三故障 80 ms 零码请求均拒绝不可观测，继续锁存；有效内码可显式清除 | [当前测量区间与回归](../experiments/p1-c2000-buck/host_c/CLEAR_MEASUREMENTS.md)、[首次闭环历史结果](../experiments/p1-c2000-buck/host_c/CLOSED_LOOP.md) |
| P2 进程 CPU 与 RTL 延迟 | 9 组主机 CPU/墙钟测量；6 组 FIFO 端口独立观测、986 周期及 570 字事件；固定背压下首次呈现至输出最大 6/13/41 时钟 | [主机测量](../experiments/p2-zcu104-daq/ps/daq_queue.md)、[RTL 测量](../experiments/p2-zcu104-daq/rtl/fifo_latency.md) |
| DAB 连续物理闭环 | 固定载波、持久节点、重叠死区、同刻保护优先；55 项测试、16 固定角回归、6 份完整波形；换向 4.15 ms、饱和返回 3.70 ms，过流峰值约 1.655 A | [物理闭环及范围](../experiments/p4-dab/CONTINUOUS_CONTROL.md) |

## 可以复述的实际问题

Buck 首次 PI 参数未满足启动要求：保留原失败数据，在隔离副本调参后按相同条件重跑。后续参数扫描又表明降低最大偏差可能牺牲恢复速度，因此没有把一个候选称为全局最优。[首次失败记录](../experiments/p1-c2000-buck/evidence/simulation-attempt1/)

Buck 旧标量判据会接受负压被截成零、电流量化跨过 0.1 A 的清除请求。修复只从原码和声明标度形成可观测标记及完整码箱上界，阈值不变，不使用仿真真值或等待时间放行。零码信息缺口仍在，故不能声称完成硬件安全恢复；C 换算函数已在主机定向执行，目标 ADC/ISR 仍未执行。[反例、有效内码与目标重编译](../experiments/p1-c2000-buck/host_c/CLEAR_MEASUREMENTS.md)

P2 首次主机联测在 WSL 路径转换处失败，而非 RTL 或 C 算法错误。直接执行模式保留 Windows 路径参数后，真实采集数据和 C 故障矩阵通过；失败日志与成功记录分别保存。[初始日志](../experiments/p2-zcu104-daq/results/frame_validator/runner_failure.log)

P2 队列测量的原终点在内容检查与释放之前，与文档定义不符。保存原源码及数据后，把终点移到成功释放之后，在隔离副本完成 9 组定向复测；当前报告只使用修复后的计时。[修复记录](../experiments/p2-zcu104-daq/ps/daq_queue.md)

DAB 过流清除后直接请求反向功率，导致再次锁存。保持 1.6 A 阈值，将恢复演示改为更慢的指令斜坡，并保留快速恢复再次跳闸的回归测试；不能通过增大阈值把这次失败隐藏掉。[定位记录](../experiments/p4-dab/diagnostics/transient_failure_01/README.md)

DAB 连续死区曾漏掉“先越轨、再因电流反向返回”的钳位事件；上下轨各越界约 0.413 V，能量残差仍很小。先定位电流过零再搜索更早的钳位，修复后粗步结果与 1 ns 参考一致。新增回归在原代码失败，修复后完整测试通过；没有放宽物理判据。[原反例及修复](../experiments/p4-dab/diagnostics/continuous_event_01/README.md)

## 还不能据此宣称的内容

尚无 C2000 固件烧录、目标 ISR 测时或真实电源测量；真实目标编译没有证明引脚映射、量程和硬件 Trip 行为。尚无完整 Vivado 构建、ZCU104 器件时序、A53 BSP 编译、DMA 到 DDR 板端收数、cache 一致性或板端吞吐。DAB 采用独立教学参数，没有完整复现 Toshiba RD264，局部死区结果不能证明整机效率或实物 ZVS。

软件工具也有未完成项：LTspice 尚无仿真结果，Simulink 脚本尚无 MATLAB 运行结果；PLECS 5.0.7 已启动但应用审批超时，未进入 Demo 或运行模型。P2 新入口也没有产生真实 Vivado/BSP 结果。不能把剩余工作统称为“只差上板”。[集中工具与阻碍](../verification/tooling/README.md)、[P2 工具链](../experiments/p2-zcu104-daq/vivado/toolchain_2025_2.md)、[P4 原生模型状态](../experiments/p4-dab/plecs/README.md)
