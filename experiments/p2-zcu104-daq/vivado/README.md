# ZCU104 工程入口与当前验证范围

当前入口已接入 AXI4-Lite 控制 wrapper，增加真实 Vivado 地址导出脚本，并提供 PS 正常启停/重启的主机验证流程；见 [当前集成说明、依赖和数据流教学](../ps/daq_session.md)。完整 Vivado/BSP 仍不可用，工程连接是待工具执行的 Tcl。

## 已执行与未执行

[daq_stream_top.v](../rtl/daq_stream_top.v) 用可综合 RTL 写法直接封装现有 source 和同步 FIFO；默认每帧 7 字、FIFO 深度 3，输出 32 位 AXI-Stream。增加 Vivado 接口属性，便于以 RTL module reference 加入块设计。没有添加寄存器组、ADC、DMA 行为模型或跨时钟逻辑。

实际执行了顶层 RTL 采集与主机 C 联测：[结果](../results/top_integration/summary.json)。Icarus Verilog 13.0 接收 12 帧、84 字、336 字节，第 137 个仿真周期完成采集；随后对下一个已提出的字施加背压，检查保持 5 个时钟。C 的 16 项故障测试在 WSL GCC 11.4.0、ASan/UBSan 下全部通过。

顶层是连续数据源。采集达到 12 个完整帧后，testbench 停止接受新字，而不是关闭源或声称 FIFO 排空；原有 FIFO 单元测试继续保留最终排空和数量守恒检查。这个改变使联测实际经过可综合顶层，而不在 source 与 FIFO 之间插入采集计数门控。

本机检查到的 AMD 工具是 Vivado Lab 2025.2，没有在已检查的安装目录/PATH 找到完整 Vivado/xsim。三个 Tcl 文件仅通过 Tcl 8.6.15 的 `info complete` 文本完整性检查；该命令不执行脚本，不能验证 Vivado 命令、IP 参数、块设计、综合或 DDR 联通。详见 [文本检查日志](../results/daq_integration/tcl_text_check.log) 和 [工具记录](../results/top_integration/vivado_availability.log)。

## 最小工程结构

```text
daq_axi_lite(source → FIFO) → AXI DMA S_AXIS_S2MM
                                     │ M_AXI_S2MM
                                     ▼
                                SmartConnect → PS S_AXI_HP0_FPD → PS DDR

PS M_AXI_HPM0_LPD → SmartConnect 1×2 → DMA S_AXI_LITE / wrapper S_AXI
PS pl_clk0 → 整个 PL 通路（请求 100 MHz；尚未进行时序分析）
PS pl_resetn0 → proc_sys_reset → DMA / SmartConnect / wrapper AXI-Lite
DMA s2mm_prmry_reset_out_n → wrapper stream_resetn（仅采集状态、source + FIFO）
```

控制使用 1×2、数据使用 1×1 SmartConnect，让工具处理 AXI 接口宽度/协议适配。HP0 是非一致性通路，CPU cache 的处理仍由软件/驱动负责。使用 PS 自带 DDR 控制器与官方板卡 preset，不新增 PL DDR MIG。

`create_project.tcl` 创建工程、调用 `create_bd.tcl`、请求 BD 校验、生成 IP 输出和 HDL wrapper，并导出 BD Tcl。它不包含综合、实现、bitstream、硬件连接或编程命令。脚本由本项目编写，不是 AMD 已验证的参考工程。

## 官方依据与本项目选择

核对日期：2026-11-04。

| 项目 | 脚本采用值及依据 |
| --- | --- |
| 板卡/器件 | `xilinx.com:zcu104:part0:1.1`、`xczu7ev-ffvc1156-2-e`；依据 AMD [XilinxBoardStore 2025.2 board.xml](https://github.com/Xilinx/XilinxBoardStore/blob/2025.2/boards/Xilinx/zcu104/1.1/board.xml) 的 vendor/name/component/file_version |
| DDR/MIO、PL0 | 应用 ZCU104 board preset；PL0 请求 100 MHz，对应官方 [preset.xml](https://github.com/Xilinx/XilinxBoardStore/blob/2025.2/boards/Xilinx/zcu104/1.1/preset.xml)；不手抄 DDR 时序 |
| PS 接口 | HPM0_LPD 用于控制，HP0_FPD 用于写入内存；[PG201 Slave Interface 表](https://docs.amd.com/r/en-US/pg201-zynq-ultrascale-plus-processing-system/Slave-Interface) 明确 HP0～HP3 到 DDR 的非一致性路径；HPM0_LPD 的 Tcl 参数及连法参照 AMD [2025.2 EDT Tcl](https://github.com/Xilinx/Embedded-Design-Tutorials/blob/2025.2/docs/Getting_Started/ZynqMPSoC-EDT/ref_files/design1/edt_zcu102.tcl)，仅取接口用法，不取 ZCU102 的板卡参数 |
| AXI DMA 7.1 | `c_include_sg=0`、`c_micro_dma=0`、`c_include_mm2s=0`、`c_include_s2mm=1`；本项目选择普通 Simple S2MM 单通道、无控制/状态流；[PG021 User Parameters](https://docs.amd.com/r/en-US/pg021_axi_dma/User-Parameters) 给出参数对应关系 |
| DMA 位宽/时钟 | stream 与 memory data 均选 32 位，地址宽度选 64 位，DRE 关闭，最大 burst 16，异步时钟选项关闭；这些是本项目取值，不是板端性能结果。依据同一 PG021 参数表及 [Clocking](https://docs.amd.com/r/en-US/pg021_axi_dma/Clocking) |
| SmartConnect 1.0 | `NUM_SI=1`、`NUM_CLKS=1`；控制 `NUM_MI=2`，数据 `NUM_MI=1`；[PG247 参数表](https://docs.amd.com/r/en-US/pg247-smartconnect/Design-Parameters) 和 [1×1 模式](https://docs.amd.com/r/en-US/pg247-smartconnect/SmartConnect-1x1-Mode) |
| 复位 | `proc_sys_reset:5.0`，PS 输入低有效，辅助输入高有效并接 0；PL0 已由 PS 提供，lock 接 1。依据 [PG164](https://docs.amd.com/v/u/en-US/pg164-proc-sys-reset)；DMA `axi_resetn` 的最小 16 个最慢时钟与同步要求见 [PG021 Resets](https://docs.amd.com/r/en-US/pg021_axi_dma/Resets)；流侧 reset 输出见 [PG021 Ports](https://docs.amd.com/r/en-US/pg021_axi_dma/Port-Descriptions) |
| RTL 接口属性 | 时钟关联 `M_AXIS/aresetn`、低有效 reset 及各 AXIS 信号；依据 [UG994 RTL 控制信号推断](https://docs.amd.com/r/en-US/ug994-vivado-ip-subsystems/Inferring-Control-Signals-in-a-RTL-Module) |

脚本指定 `zynq_ultra_ps_e:3.5`、`axi_dma:7.1`、`smartconnect:1.0`、`proc_sys_reset:5.0`、`xlconstant:1.1`。当前没有 IP catalog 可执行核对，因此完整 Vivado 中的版本可用性、属性名和参数传播仍属于下列待验证项。`vendor/embeddedsw-xilinx_v2025.1` 只是先前保存的源码，尚未作为 2025.2 BSP 编译使用。

## Simple S2MM：一帧怎样对应一次接收

当前源在每 7 个 32 位字的最后一字拉高 TLAST，每字 TKEEP 为 `f`，所以一个流包为 **28 字节**。未来最小接入选择一次 Simple S2MM 接收一个这样的包：提供对齐的有效目的缓冲区，将容量设为 28 字节，目的地址配置后最后写长度以启动。接收完成后检查错误及完成状态，并确认实际写入长度为 28。PG021 规定接收长度至少容纳最大预期包，完成后 S2MM_LENGTH 更新为实际写入字节数。依据：[Simple DMA 编程顺序](https://docs.amd.com/r/en-US/pg021_axi_dma/Direct-Register-Mode-Simple-DMA)、[S2MM_LENGTH](https://docs.amd.com/r/en-US/pg021_axi_dma/S2MM_LENGTH-S2MM-DMA-Buffer-Length-Register-Offset-58h)、[S2MM_DMASR 完成位](https://docs.amd.com/r/en-US/pg021_axi_dma/S2MM_DMASR-S2MM-DMA-Status-Register-Offset-34h)。

这不是“设 336 字节就自动合并 12 个 TLAST 包”。本步的 336 字节文件来自 testbench 连续接收 12 个流包；没有实例化或模拟 AMD DMA。将来若按上述 Simple 路径采集 12 帧，应分别确认 12 次包接收，并依次把 CPU 已拥有的有效 payload 送入同一个 C 校验状态，最后 `fv_finish(&state, 12)`。只在整个采集周期开始时 reset 校验器，不在每帧之间 reset。软件也可以把多个已完成、按序的缓冲区合批，或把一帧的 CPU 视图分成 4 字节整数倍的小批次；这不改变硬件包边界。相关 cache/所有权说明见 [ps/README.md](../ps/README.md)。

源是可停顿的测试数据发生器；DMA 等待下一次接收时，背压可以逐级传回。此点不代表真实 ADC 不会溢出。DMA stream reset 接到顶层，目的是在 DMA 复位时同步清空源/FIFO 的采集周期；实际软复位传播、首次有效字与复位脉宽仍需完整 IP 仿真核实。软件不能只清 C 状态就声称硬件已开始新周期。

## 构建入口（需要完整 Vivado，尚未在本机执行）

先在完整 Vivado 2025.2 配好 Zynq UltraScale+ 器件支持及上述官方 ZCU104 board files。`vivado` 必须指完整工具而非 `vivado_lab`。从实验根目录执行：

```powershell
New-Item -ItemType Directory -Force .\results\vivado_build | Out-Null
vivado -mode batch -source .\vivado\create_project.tcl -log .\results\vivado_build\vivado.log -journal .\results\vivado_build\vivado.jou
```

计划产物在 `build/vivado_zcu104/`，包括 `.xpr`、`daq_bd.bd`、生成的 wrapper、`daq_bd_export.tcl`，以及从实际地址段导出的 `address_map.csv` 和 `daq_addresses.h`。本次没有这些实际产物。脚本不自动替换已有同名工程；重新构建时可调整 `build_dir` 另建目录。

现有环境可实际运行的命令：

```powershell
& 'E:\python.exe' .\scripts\run_frame_validator.py --output results/top_integration_recheck
& 'E:\python.exe' .\scripts\check_tcl_text.py
```

## 具体待验证项

- 在完整 Vivado 中执行三个 Tcl，确认板卡 preset、PS 的 HP0/HPM0 配置、module reference 的 AXIS/AXI-Lite 推断和 IP 参数被接受。
- 执行真实 `validate_bd_design` 与输出生成；审阅地址分配、接口宽度、时钟和 DMA 复位传播。脚本用 `assign_bd_address`，没有虚构控制基址或 DDR 缓冲区地址。
- 在工具支持下再做实际综合、实现和时序检查；目前没有资源利用率、Fmax 或 DDR 吞吐量数据。
- BSP/FSBL/驱动、缓冲区分配和 cache 交接、Simple S2MM 每包完成与超时恢复仍未实现或运行；板端 DDR 读写和所有硬件操作未执行。
