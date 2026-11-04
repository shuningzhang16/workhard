# 已运行结果与证据入口

以下均为离线仿真或主机验证，参数与适用范围以各实验说明为准。

| 工作 | 已取得的结果 | 证据 |
| --- | --- | --- |
| Buck 平均模型 | 默认 PI 下启动、负载与输入阶跃满足原响应检查；负载恢复 5.12 ms | [原始 CSV](../experiments/p1-c2000-buck/simulation/results/)、[测试](../experiments/p1-c2000-buck/simulation/test_buck.py) |
| Buck PI 比较 | 9 组增益中 3 组满足原条件；候选最差扰动偏差降低约 15%，最差恢复时间略增，默认值保留 | [参数比较](../experiments/p1-c2000-buck/simulation/PI_COMPARISON.md) |
| Buck 故障恢复 | 平均模型的过流、过压、欠压锁存和显式恢复；故障期间保留电感/电容状态 | [保护说明](../experiments/p1-c2000-buck/simulation/PROTECTION.md) |
| Buck PWM 开关 | 50 kHz、固定占空比稳态约 2 V；细步长纹波 0.752145 mV、0.141422 A；控制负载阶跃恢复 5.10 ms | [开关说明与数据](../experiments/p1-c2000-buck/simulation/SWITCHING.md) |
| Buck 独立 SPICE 对照 | ngspice 36 实际运行；8 项对照检查通过。整个稳态窗口的输出/电感纹波与 Python 分别相差约 −0.0412%/−0.00534% | [SPICE 报告](../experiments/p1-c2000-buck/simulation/SPICE_COMPARISON.md) |
| AXI-Stream 数据源 | 帧长 1/7/16、背压稳定、复位及 16 位序号回绕 | [RTL 结果](../experiments/p2-zcu104-daq/results/first_step/summary.json) |
| 同步 FIFO | 深度 1/3/16、非 2 的幂指针回绕、满时同时读写、复位丢弃量均逐拍核对 | [FIFO 结果](../experiments/p2-zcu104-daq/results/fifo_step/summary.json) |
| 主机 C 帧校验 | 实际 RTL 的 12 帧、84 字、336 字节；16 项故障测试通过 ASan/UBSan | [结果汇总](../experiments/p2-zcu104-daq/results/frame_validator_repair/summary.json)、[故障矩阵](../experiments/p2-zcu104-daq/results/frame_validator_repair/fault_matrix.csv) |
| 顶层与 Vivado 入口 | source/FIFO 顶层实际经过 RTL→C 联测；ZCU104 Tcl 已提供，仅做文本完整性检查，未生成或验证真实块设计 | [工程入口及限制](../experiments/p2-zcu104-daq/vivado/README.md)、[顶层联测](../experiments/p2-zcu104-daq/results/top_integration/summary.json) |
| DAB SPS | 3 个电压比、39 个相移点；匹配电压 ±30° 时传输 ±20 W | [扫描与波形](../experiments/p4-dab/results/RESULTS.md) |
| DAB EPS 比较 | 同功率比较保留未改善和无解工况；电压比 0.75、±2.7 W 时 RMS 电流降低 31.183% | [EPS 结果](../experiments/p4-dab/results_eps/RESULTS.md) |
| DAB 瞬态与保护 | 四工况保留跨周期电流；换向、采样锁存、显式清除及能量收支通过 | [瞬态结果](../experiments/p4-dab/results_transient/RESULTS.md) |
| DAB 换流极性 | 40 个周期波形、320 个桥臂事件；电压比 0.75、±2.7 W 的所选 EPS 满足全部必要极性，仍不能确认 ZVS | [逐沿分析](../experiments/p4-dab/COMMUTATION.md) |

## 可以复述的实际问题

Buck 首次 PI 参数未满足启动要求：保留原失败数据，在隔离副本调参后按相同条件重跑。后续参数扫描又表明降低最大偏差可能牺牲恢复速度，因此没有把一个候选称为全局最优。[首次失败记录](../experiments/p1-c2000-buck/evidence/simulation-attempt1/)

P2 首次主机联测在 WSL 路径转换处失败，而非 RTL 或 C 算法错误。直接执行模式保留 Windows 路径参数后，真实采集数据和 C 故障矩阵通过；失败日志与成功记录分别保存。[初始日志](../experiments/p2-zcu104-daq/results/frame_validator/runner_failure.log)

DAB 过流清除后直接请求反向功率，导致再次锁存。保持 1.6 A 阈值，将恢复演示改为更慢的指令斜坡，并保留快速恢复再次跳闸的回归测试；不能通过增大阈值把这次失败隐藏掉。[定位记录](../experiments/p4-dab/diagnostics/transient_failure_01/README.md)

## 还不能据此宣称的内容

尚无 C2000 固件烧录或真实电源测量；Python 保护没有证明硬件 Trip 行为。尚无 ZCU104 综合后时序、DMA 到 DDR 板端收数、cache 一致性或板端吞吐。DAB 采用独立教学参数，没有完整复现 Toshiba RD264，也没有器件损耗、转换效率或完整 ZVS 验证。仓库保留这些边界，是为了让每个结果能对应到真正执行过的代码和数据。
