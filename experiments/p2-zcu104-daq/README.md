# P2：ZCU104 FPGA 数据采集学习项目

当前阶段：已实现内部数据源/FIFO、AXI4-Lite 控制、逐包接收、C 校验及有界消费队列。控制 wrapper 已接入 Vivado Tcl，并提供地址导出及 PS 启停/重启流程。RTL、主机严格 C 测试及明确标记的主机队列测量通过；完整 Vivado 尚未执行，Standalone 草稿未编译，没有实际地址导出、BSP 或 DDR 联通结果，原厂代码保留不变。

## 第七小步第二阶段：有界多缓冲消费与主机统计

新增 [daq_queue](ps/daq_queue.md)：固定 DMA 工作缓冲区，每包同步和校验成功后复制进容量 1～8 包的 CPU 环形队列。满队列不再提交 DMA，消费者未释放的槽不被覆盖；STOP 排空包同样逐包入队。故障保留有效前缀，队列清空后才允许显式重启，原接收错误和所有权判据保留。

实际完成 **13/13** 新队列故障/顺序测试，严格编译及 ASan/UBSan 通过；上游 session **9/9**、接收 **13/13**、校验 **16/16** 与 RTL 回归也通过。当前容量 1/3/8 × 消费等待 0/200/1000 µs 的 **9/9** 组主机测量补齐进程 CPU 时间和单核等效 CPU/墙钟占比；零等待组实际重放 10 万个周期，窗口约 0.43～0.45 秒。本轮复用旧 RTL payload，重跑 13 项队列测试通过，未重复上游测试；结果不是板端吞吐或全机 CPU 使用率。零等待 CPU 原始比值略高于 100%，保留了独立时钟核查及解释限制。

- [当前结果汇总](results/performance_cpu/summary.json)、[13 项故障矩阵](results/performance_cpu/fault_matrix.csv)、[含 CPU 的主机测量 CSV](results/performance_cpu/host_measurements.csv)。
- [所有权、满队列策略、测量定义和教学数据流](ps/daq_queue.md)。
- 统一入口：`python scripts/run_daq_queue.py --output results/daq_queue_recheck`；默认包含原 session 入口，无需再重复调用。

首次检查发现延迟终点取在内容核对和释放之前，已修正为成功 `dq_release` 后采时；当时隔离副本严格编译及 **9/9** 组定向复测通过。[修复前源码](results/queue_timing_before/bench_daq_queue.c)、[修复前测量](results/queue_timing_before/host_measurements.csv)、[仅修正计时后的测量](results/queue_timing_fixed/host_measurements.csv) 与原 `results/daq_queue` 的 13 项功能测试证据均保留。

新增 **6/6** 组 [固定背压 RTL 测量](rtl/fifo_latency.md)：深度 1/3/16，连续接收及固定 3/8 接收；公开端口记录首次呈现、入口握手、出口握手，独立队列统计峰值，每 epoch 单列接受/输出/复位丢弃/待输出。固定背压的首次呈现至输出最大延迟为 **6/13/41 时钟**，6 组最终待输出均为 0。[结果 CSV](results/performance_fifo_boundaries/measurements.csv) 及所有周期、每字去向已保存。源被背压暂停不等于不可停顿 ADC 丢样；未改可综合 RTL。复现：`python scripts/run_fifo_latency.py --output results/fifo_latency_recheck`。

## 第七小步第一阶段：工程连接与 PS 启停流程

控制 SmartConnect 扩为 1×2，分别连接 DMA 与 wrapper；增加 [实际地址导出脚本](vivado/export_addresses.tcl)。系统复位保留 AXI-Lite 通道，DMA 流侧复位只清采集状态，避免 DMA reset 期间无法读取控制寄存器。

[daq_session](ps/daq_session.md) 复用既有接收核心：先提交 DMA、确认流侧复位释放、再 START；STOP 后有界排空并同时核对硬件帧数和原定采集目标；错误保持锁存，显式重启失败不回收设备缓冲区。附控制寄存器→DMA→校验的数据流说明及具体 BSP/工具依赖。

实际结果：**9/9** 新增主机流程测试、原接收 **13/13**、原校验 **16/16** 通过严格编译及 ASan/UBSan；扩展 RTL TB 完成 **26 写、55 读、77 字/11 帧**，包括采集复位期间 R 响应保持和状态读取。[最终结果](results/daq_integration/summary.json) 与日志已保存。

统一入口：`python scripts/run_daq_session.py --output results/daq_session_recheck`。三个 Tcl 仅做文本完整性检查，不把它称为 Vivado 执行。第一阶段到此形成可提交点；后续第二阶段再增加有界多缓冲接收/消费和明确标记的主机性能统计。

## 第六小步：AXI4-Lite 启停和统计

新增独立 [daq_axi_lite.v](rtl/daq_axi_lite.v)，在现有连续流顶层之外提供启停、停止后的清计数/重启，以及输出已接收字、帧和停顿计数。STOP 等待 TLAST 握手，不撤回被反压的有效拍；继续保留序号，显式重启才回到帧 0。现有 source/FIFO/top 与其测试均未修改。

本阶段的历史 [TB 记录](results/axi_lite/summary.json) 为 **23 次写、46 次读、70 字/10 帧输出**；AW 先到/W 先到/同拍分别 5/3/15 次，B/R 反压分别 33/161 周期。覆盖 WSTRB、响应稳定性、连续并行读写、独立计数核对、帧边界停止和重启。当前扩展 TB 的新结果见上方第七小步。

原 source/FIFO 六组回归也已实际复跑并全部通过，见 [回归汇总](results/axi_lite_regression/summary.json)。

- [寄存器表、PS 使用次序及验证范围](rtl/daq_axi_lite.md)。
- [结果汇总](results/axi_lite/summary.json)、[总线 CSV](results/axi_lite/axi_transactions.csv)、[流周期 CSV](results/axi_lite/stream_cycles.csv)。
- 复现：`python scripts/run_axi_lite.py --output results/axi_lite_recheck`。

这是实际可仿真的寄存器接口；未进行该 wrapper 的 Vivado 集成、PS BSP 或 DDR 联通验证，没有板端吞吐或时序结论。

## 第五小步：逐包接收控制与主机故障验证

[simple_s2mm.c](ps/simple_s2mm.c) 每次提交 28 字节，有限轮询，检查错误、完成与实际长度后才把缓冲区交回 CPU 并调用原校验器。错误锁存，重启须显式调用；重启失败保留原错误及设备所有权。平台仅提供五个操作，不包含描述符环或完整 DMA 模型。

实际重新采集 **84 个 RTL 输出字**：原校验器 **16/16**、新增接收流程 **13/13** 测试通过，GCC 严格警告检查及 ASan/UBSan 通过。覆盖连续 12 包、最后一次轮询完成、零/短/超容量长度报告、DMA 错误、超时、校验失败、提交失败、提前结束、重启失败及显式重启后完整采集。主机注入状态只验证控制流程、边界与调用顺序，不证明 DMA、cache 或 DDR 联通。

- [完整中文说明及官方依据](ps/simple_s2mm.md)、[可移植接口](ps/simple_s2mm.h)、[Standalone 草稿](ps/standalone_s2mm_draft.c)。
- [结果汇总](results/simple_s2mm/summary.json)、[故障矩阵](results/simple_s2mm/fault_matrix.csv)、[主机测试](tests/test_simple_s2mm.c)。
- 复现：`E:\python.exe scripts/run_simple_s2mm.py --output results/simple_s2mm_recheck`。

## 第四小步：顶层封装与 ZCU104 工程入口

[daq_stream_top.v](rtl/daq_stream_top.v) 直接连接现有 source 和 FIFO，默认每帧 7 字、FIFO 深度 3。采集 testbench 现在实际实例化该顶层，在背压下接收 **12 帧、84 字、336 字节**，第 137 个仿真周期完成采集；随后停止接收，并检查下一个有效字保持 5 个时钟。连续源仍可能在 FIFO 中留下数据，此处不声称排空；原有 FIFO 单元测试保留排空及数量守恒检查。

这些实际 RTL 输出再次送入主机 C 校验器，严格警告、ASan 和 UBSan 下 **16/16 项测试通过**。入口与证据：

- [联测脚本](scripts/run_frame_validator.py)、[结果汇总](results/top_integration/summary.json)、[RTL 运行日志](results/top_integration/rtl_simulation.log)、[C 故障矩阵](results/top_integration/fault_matrix.csv)。
- [Vivado 工程入口](vivado/create_project.tcl)、[块设计 Tcl](vivado/create_bd.tcl)、[官方依据、构建命令及待验证项](vivado/README.md)。目标链路为 `source → FIFO → AXI DMA S2MM → PS DDR`。
- [Tcl 文本完整性检查](results/top_integration/tcl_text_check.log)、[本机工具记录](results/top_integration/vivado_availability.log)。仅检查文本括号/引号完整性，没有执行 Vivado 命令或验证 IP 参数、块设计、综合、DDR 联通。

依据 PG021，未来最小 Simple S2MM 接入按 **一次接收对应一帧、28 字节** 处理完成状态及实际长度，再将各批有效 payload 按序送入同一个 C 校验状态。现有 336 字节离线文件包含 12 个 RTL 流包，不能当作一次硬件 DMA 接收。详见 [包/长度/完成语义](vivado/README.md#simple-s2mm一帧怎样对应一次接收)。

```powershell
& 'E:\python.exe' .\scripts\run_frame_validator.py --output results/top_integration_recheck
& 'E:\python.exe' .\scripts\check_tcl_text.py
```

## 第三小步：C 帧流校验与 RTL 数据联测

新增 [ps/frame_validator.c](ps/frame_validator.c) 和 [头文件](ps/frame_validator.h)，支持按批次输入、跨批次半帧、16 位帧序号回绕和显式采集周期重置。索引/序号错误锁存到 reset；结束时根据预期帧数检测截断或超额帧。没有实现 DMA 驱动。

实际运行 [完整采集 testbench](tb/tb_capture_stream.sv)，获得现有数据源经过深度 3 FIFO 后的 **12 帧、84 字、336 字节**。原始 CSV 和其小端序列化文件送入 [C 故障测试](tests/test_frame_validator.c)。WSL Ubuntu-22.04 / GCC 11.4.0 启用 AddressSanitizer、UBSan 和严格警告检查后，**16/16 项测试通过**。

结果与复现入口：

- [结果汇总](results/frame_validator_repair/summary.json)、[故障矩阵 CSV](results/frame_validator_repair/fault_matrix.csv)、[完整 RTL 轨迹](results/frame_validator_repair/rtl_capture.csv)。
- [C 接口、数据来源、DMA/cache/超时接入边界](ps/README.md)。
- 运行：`E:\python.exe scripts/run_frame_validator.py --output results/frame_validator_recheck`。

首轮 WSL 路径转换失败已保存证据，并在隔离副本修复验证后应用正式脚本；因此本次成功证据放在 `results/frame_validator_repair/`。这一步是 RTL 数据与 x86_64 主机 C 的离线联测，不是 PS 实测；回绕专项另用明确标记的 C 人工数据。原有 source/FIFO 测试保持不变。

## 第二小步：单时钟 FIFO

本步实际仿真链路：`原有数据源 → testbench 合法空拍/字节掩码刺激 → 同步 FIFO → 独立队列检查器`。没有引入 DMA、AXI-Lite 或跨时钟逻辑。

| 文件 | 用途 |
| --- | --- |
| [rtl/axis_sync_fifo.v](rtl/axis_sync_fifo.v) | 32 位、单时钟、可配置深度的 AXI-Stream FIFO |
| [tb/tb_axis_sync_fifo.sv](tb/tb_axis_sync_fifo.sv) | 数据源接入 FIFO，动态队列逐字核对、定向满/空及复位测试 |
| [scripts/run_sim.py](scripts/run_sim.py) | 新增 `--suite source/fifo/all`，默认仍执行原有 source 测试 |
| [results/fifo_step/summary.json](results/fifo_step/summary.json) | 三组 FIFO 测试及三组 source 回归的实际结果 |
| `results/fifo_step/depth{1,3,16}/` | 编译日志、仿真日志、占用与握手的有限原始 CSV |

### 实现与检查方法

FIFO 把 `{TLAST, TKEEP, TDATA}` 作为一个 37 位字存储，读写指针遇到 `DEPTH-1` 显式回零，因此允许非 2 的幂的深度。占用数只在单独读或单独写时变化，同时读写保持占用数。满时如果下游同拍读走一个字，允许上游同拍写入；深度 1 同样适用。空时不组合直通，新字在写入后的周期有效。低有效同步复位使占用和指针清零，不清内存；`TVALID=0` 时数据总线不具有有效数据含义。

这是用于小深度的异步读存储结构，不是针对块 RAM 的实现。满时存在输出 ready 到输入 ready 的组合路径；本次没有进行综合、资源利用率或时序收敛测量。

检查器使用独立的 SystemVerilog 动态队列，不读取 FIFO 内部计数或指针。每次输入握手追加完整的 37 位字，每次输出握手弹出并比较队头；背压时也逐周期核对输出稳定性。每个周期都核对：`输入握手数 = 输出握手数 + 复位丢弃数 + 队列剩余数`，最终排空后剩余数必须为 0。

现有数据源的 `TKEEP` 固定为 `f`，因此 testbench 在 FIFO 输入处让掩码按数据索引循环为 `f/7/3/1`，检验侧带字段是否与数据一起传递；这只是验证刺激，不改变数据源 RTL 或其原有测试。testbench 插入输入空拍时，会保持已经提出且尚未握手的字，避免用违反 valid/ready 规则的输入测试 FIFO。

测试包含：空队列、填满后的持续背压、满状态同时读写、排空、连续传输、TLAST 停留、固定种子的随机输入空拍/输出背压、满队列复位、复位后重启及最后排空。三种深度的读写次数均超过各自深度的多倍，覆盖指针反复回绕。

### 2026-11-04 实际结果

| 深度 | 占用峰值 | 输入握手 | 输出握手 | 复位丢弃字 | 最终剩余 | 输入背压周期 | 输出背压周期 | 满状态同时读写 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 684 | 683 | 1 | 0 | 184 | 234 | 555 |
| 3 | 3 | 775 | 772 | 3 | 0 | 94 | 268 | 209 |
| 16 | 16 | 983 | 967 | 16 | 0 | 27 | 313 | 95 |

六组编译与仿真全部通过，退出码均为 0；原有帧长 1、7、16 的 source 回归结果保持一致。FIFO 在定向连续读写窗口分别完成 12/12、20/20、72/72 个周期的输出握手，即每周期一个字。仿真时钟为 10 ns，仅描述该 RTL 仿真条件；不能据此声称板卡达到某个吞吐量或频率。

表中输入与输出数量的差值全由明确施加的复位解释，不是无故丢字。复位会丢弃缓冲中的部分帧和可能存在的 TLAST，下游需要同时处理复位边界。此步未增加现实 ADC 采样溢出统计。

原始 `cycles.csv` 保存前 512 个周期，并额外保存缓存非空复位及最后排空阶段；其余随机阶段仍逐拍检查，仅不全部落盘。`occupancy_before/after` 来自独立队列，代表该采样沿前/后的逻辑占用；非复位行的接口信号为上升沿更新前的值。复位行是复位更新后的观察，不用于握手计数。无效周期可能保留旧数据或显示 `x`，只在 valid 为 1 时解释数据与侧带字段。

### 复现全部回归

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p2-zcu104-daq'
& 'E:\python.exe' .\scripts\run_sim.py --suite all --output results/fifo_step
```

只跑 FIFO 可用 `--suite fifo`；只跑原数据源可用 `--suite source`。更换输出目录，例如 `--output results/fifo_recheck_01`，可保留本次证据。每组日志都记录真实命令、结果和退出码。

## 第一小步：内部数据源与仿真

| 文件 | 用途 |
| --- | --- |
| [rtl/axis_pattern_source.v](rtl/axis_pattern_source.v) | 本项目新增的 32 位 AXI-Stream 测试数据源 |
| [tb/tb_axis_pattern_source.sv](tb/tb_axis_pattern_source.sv) | 独立计数参考、协议检查和定向刺激 |
| [scripts/run_sim.py](scripts/run_sim.py) | 调用 Icarus 编译及运行三组 RTL 测试，保留命令和日志 |
| [results/first_step/summary.json](results/first_step/summary.json) | 本次实际仿真结果汇总 |
| `results/first_step/frames{1,7,16}/` | 各组编译日志、仿真日志、逐周期与已接受字的 CSV 轨迹 |

RTL 和 testbench 是本项目新增实现，未从 `vendor/` 驱动改写。Python 只负责编译和调用仿真器，不是行为参考模型。

### 数据格式与握手

- `TDATA[31:16]` 为 16 位帧序号，`TDATA[15:0]` 为帧内字索引；帧序号以 65536 为模回绕。
- `FRAME_WORDS` 为静态参数，默认 16，可取 1～65536；本次实际验证 1、7、16 三个值。每个字占 4 字节，`TKEEP=4'b1111`，末字 `TLAST=1`。
- 仅在时钟上升沿同时满足 `TVALID && TREADY` 时推进索引或帧序号。`TVALID=1, TREADY=0` 时，数据、TLAST、TKEEP 及 TVALID 都保持；有效信号不依赖 ready 才产生。依据见 [AMD 关于 AXI4-Stream 握手的说明](https://docs.amd.com/r/en-US/ug1483-model-composer-sys-gen-user-guide/AXI4-Stream-Support-in-Model-Composer)。
- `aresetn` 为低有效同步复位：复位采样沿清空计数并撤销 valid；释放后的第一个上升沿置 valid，之后才可接受首字。复位丢弃未完成帧，新数据从帧 0、索引 0 开始。下游必须同步处理该复位边界；单看数据无法区分复位与序号回绕。
- ready 连续为 1 时，每周期接受一个字，跨帧没有额外空拍。这是 RTL 行为，不是板端吞吐量。测试时钟为 10 ns 的仿真刺激，不表示已达到 100 MHz 时序收敛。

本步链路仅为：`内部测试源 → AXI-Stream → testbench 接收/检查`。测试源可以停止推进，因此背压不会产生“采样溢出”；未来实际 ADC 的连续采样与 FIFO 容量问题尚未实现。

### 复现命令

本机已将 Icarus 及小型运行库解压到 `.tools/ucrt64/`，仅限本实验目录；没有改系统 PATH。工具来自 [MSYS2 官方软件包](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-iverilog)，各包版本及 URL 见 [tool_packages.csv](results/first_step/tool_packages.csv)。`.tools/` 和 `build/` 不提交到仓库；新机器需要先具备 Icarus Verilog，脚本不会自行联网安装。也可以使用 PATH 中已有的 Icarus，或传 `--iverilog` 指定其可执行文件。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p2-zcu104-daq'
& 'E:\python.exe' .\scripts\run_sim.py
```

已有 Python 3 和 Icarus 的其他机器可在本目录运行 `python scripts/run_sim.py`。为保留先前证据，可用 `--output results/recheck_01` 保存新一次结果；默认命令会重写 `results/first_step` 下的仿真产物。每组 `compile.log` 和 `simulation.log` 记录了完整原始命令和退出码。

### 2026-11-04 实际结果

| 帧长（字） | 接受的字数 | 完整帧数 | 背压周期 | TLAST 背压周期 | 背压中复位次数 | 帧序号回绕 | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 66,314 | 66,314 | 276 | 276 | 1 | 1 | PASS |
| 7 | 849 | 121 | 276 | 35 | 1 | 0 | PASS |
| 16 | 966 | 60 | 276 | 23 | 1 | 0 | PASS |

三组检查初始 ready 长时间为低、持续接收、末字连续背压、固定种子的随机背压、背压中复位及重新开始。单字帧额外运行超过 65536 帧，实际跨越序号回绕。检查器用每次复位后累计接受字数推算期望序号与索引，不读取 DUT 内部寄存器；还检查未握手时的输出稳定性和无空拍行为。所有编译与仿真退出码均为 0。

原始数据有意限量：`cycles.csv` 保存前 2048 个时钟周期中的非复位采样，表示上升沿更新前的接口值；`transfers.csv` 保存最初 4096 个实际握手字，并在单字帧测试中另外保存回绕附近的字。因此单字帧 CSV 中间存在主动省略区间，不是丢帧。其 `epoch` 区分复位区间，`ordinal` 是该区间内从 0 开始的已接受字编号；`data_hex` 为十六进制，`keep`、`last` 为十进制。检查器仍逐拍检查全部仿真，未因限量保存而跳过检查。

完整帧数按已接受的 TLAST 计数；复位前未完成帧及结束时可能未完成帧不计入完整帧，因此总字数不一定等于帧数乘帧长。本次没有运行 FPGA 综合、时序分析、厂商 VIP、DMA/DDR 或硬件测试。

## 本次取得的内容

来源为 AMD/Xilinx 官方 [embeddedsw 仓库](https://github.com/Xilinx/embeddedsw)，版本标签为 [xilinx_v2025.1](https://github.com/Xilinx/embeddedsw/releases/tag/xilinx_v2025.1)。选用该明确版本便于追溯，不表示本机工具版本已与其匹配。

`vendor/embeddedsw-xilinx_v2025.1/` 保留上游相对路径：

| 路径 | 内容 |
| --- | --- |
| `XilinxProcessorIPLib/drivers/axidma/src/` | 完整的驱动源码目录，共 13 个文件；包含 Simple DMA、SG 描述符/环管理、寄存器定义及原厂构建文件 |
| `XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c` | Simple DMA 轮询回环示例，包含缓冲区准备、cache 操作、双向 DMA 提交及接收数据校验 |
| `LICENSES/MIT` | 上游 MIT 许可证原文 |

逐文件来源 URL、路径、字节数及下载检查结果见 [sources.csv](sources.csv)。取回日期为 2026-11-04（Asia/Shanghai）。所有 vendor 文件均直接下载保存，未修改内容、换行或版权声明。

## 许可与来源边界

这些文件是 AMD/Xilinx 原厂材料，不是个人原创实现。C 源文件、头文件和 `CMakeLists.txt` 中的原始版权及 `SPDX-License-Identifier: MIT` 均已保留；许可证全文见 [LICENSES/MIT](vendor/embeddedsw-xilinx_v2025.1/LICENSES/MIT)。原厂 `Makefile` 本身没有 SPDX 行，本次也没有补写或更改它。

本次未引入 ADI HDL 工程，没有声明任何 ADI 工程已适配 ZCU104。后续若引入 ADC/FMC 子卡，需另行核对 ADI 工程的载板、器件、时钟、接口和约束。

## 原厂材料检查与适配限制

- 已实际下载 15 个上游文件，共 205,014 字节；每个文件长度与同版本 GitHub Contents API 返回值一致。结果记录于 `sources.csv`。这只是文件获取检查，不是功能验证。
- 官方示例要求 AXI DMA 的两个 AXI-Stream 方向之间存在硬件回环，并采用 Simple DMA 模式。其代码不是内部数据发生器，也不是单独可运行的电脑程序。
- 这里保存的是驱动源码和一个示例的子集，不包含完整 embeddedsw、Standalone BSP、生成的 `xparameters.h`、板级配置、链接脚本或 Vivado 硬件设计。`src/xaxidma_g.c` 不能当作已生成的 ZCU104 配置使用。
- 已完成 source/FIFO 顶层 RTL 与可供 PS/主机复用的 C 校验模块联测，并提供 Vivado FIFO/DMA/DDR 块设计 Tcl 入口；尚未在完整 Vivado 中生成或验证块设计，也未实现板端应用。没有板端吞吐量、延迟或丢帧率测量结果。
- `E:\AMDDesignTools\2025.2` 中发现 Vivado Lab，未找到 xvlog/xelab/xsim 可执行文件；没有将 Lab Edition 称作可用的完整仿真工具链。本次实际用的是本目录 Icarus Verilog 13.0。
- PATH 中的 `E:\Scripts\python.exe` 报告缺少 `pyvenv.cfg`，实际使用正常的 `E:\python.exe`（3.14.4），未改动系统设置。首次 Python 下载请求发生 TLS EOF，改用 PowerShell 从 MSYS2 官方镜像成功取回；没有关闭 TLS 校验，记录见 [tool_setup.log](results/first_step/tool_setup.log)。

## 如何开始阅读

先阅读 [原始轮询示例](vendor/embeddedsw-xilinx_v2025.1/XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c)，依次跟踪初始化、禁用中断、cache flush、接收/发送提交、轮询及 cache invalidate 后的数据校验。API 含义可参照 [AMD AXI DMA 驱动文档](https://xilinx.github.io/embeddedsw.github.io/axidma/doc/html/api/index.html)；该文档网站可能随上游更新，本目录源码以 `xilinx_v2025.1` 为准。

查看本次原始文件清单，可在本目录执行：

```powershell
Import-Csv .\sources.csv | Format-Table upstream_path, bytes, result -AutoSize
```

## 下一小步

原厂源码仍保留在 `vendor/` 且未改动。第七小步第二阶段（有界队列与主机统计）已完成，交由协调聊天单独提交。根目录保存的 [综合网表重放证据](../../verification/yosys-control/README.md) 对应其记录的源码版本；本阶段未改 RTL。完整 Vivado/BSP 和真实 DMA/DDR 验证仍受工具与目标依赖限制。当前未执行上板、写卡或硬件重跑操作。
