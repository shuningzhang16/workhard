# AXI4-Lite 控制与状态寄存器

[daq_axi_lite.v](daq_axi_lite.v) 是独立 wrapper，内部实例化原有 `daq_stream_top`。原 source、FIFO、连续流顶层、既有 testbench 和运行入口均未修改。本步只实现并实际仿真寄存器/流接口，没有把 wrapper 接入 Vivado 块设计，也没有 PS BSP、基址或 DDR 验证。

同一 `aclk` 驱动 AXI4-Lite 和 AXI-Stream；低有效 `aresetn` 在上升沿采样。复位后输出停止、计数清零、总线响应撤销。默认每帧 7 字、FIFO 深度 3；本步实际测试该配置。

## 寄存器表

AXI4-Lite 数据宽度 32 位，地址输入为 6 位本地字节偏移（64 字节范围）。以下不是 PS 物理地址。所有寄存器均按 4 字节对齐；未列出或未对齐的地址返回 `SLVERR`，读数据为 0。正常响应为 `OKAY`。

| 偏移 | 名称 | 读写 | 定义 |
| --- | --- | --- | --- |
| `0x00` | CONTROL | RW | bit 0：写 1 开始/继续，写 0 请求帧边界停止；读值是当前运行请求，即 running 且没有 stop_pending |
| `0x04` | STATUS | RO | bit 0：running；bit 1：stop_pending；停止后两位均为 0 |
| `0x08` | COMMAND | WO，读 0 | bit 0 写 1：重启 source/FIFO 并清计数，保持停止；bit 1 写 1：仅清计数；两位均为 0 时无动作 |
| `0x0c` | WORDS | RO | 本 wrapper 输出端 `TVALID && TREADY` 的字数 |
| `0x10` | FRAMES | RO | 输出端被接受的 TLAST 数 |
| `0x14` | STALLS | RO | 输出端 `TVALID && !TREADY` 的时钟周期数 |

计数器为 32 位自然模加；没有饱和、溢出中断或锁存快照组。未启用输出时不算停顿；FIFO 内部预取的字不算已接收字。运行中分别读取多个计数器不保证它们来自同一个时刻；需要一致的停止统计时，先等 STATUS 为 0 再读取。

CONTROL/COMMAND 仅低字节有定义，只有 `WSTRB[0]=1` 才会执行其中的位；其他字节和保留位被忽略。`WSTRB=0` 对合法可写地址无作用且返回 OKAY。向只读或非法地址写入返回 SLVERR。COMMAND 是写 1 动作，不保存命令值；同时写两位等价于重启并清计数。

清计数和重启只在 `running=0` 时生效；运行或待停止时写入任一有效命令返回 SLVERR 且不执行，避免撤销被反压的有效拍、拆开输出帧或让在途数据静默跨越采集周期。掩码关闭的命令不触发此错误。`AxPROT` 不用于权限判断，本实验外设不实现访问隔离。

## 启停和重启语义

- START 打开输出。停止状态下 FIFO 可能已预取数据，开始后可立即提出有效拍；有效信号不等待 ready。
- STOP 设置 stop_pending，继续呈现已经提出的有效拍，并在接受下一次 TLAST 时关闭输出。请求即使到达被反压的第一字或 TLAST，也不会撤回 valid 或改变该字。若 STOP 恰与 TLAST 握手在同一提交沿生效，就停在该边界。
- STOP 完成后，预取的下一帧留在 FIFO。再次 START 继续序号；清计数同样不清数据或序号。START 可取消尚未完成的 STOP。
- RESTART 在停止时产生一个同步流水线复位脉冲，丢弃预取数据，清计数，保持输出关闭。下一次 START 从帧 0、索引 0 开始。

停止依赖下游继续接受当前帧。若下游长期不 ready，STATUS 可以持续为 3；不能把写 CONTROL=0 的 B 响应当作“已停”。软件应有限轮询 STATUS，并依据实际 DMA 状态处理不能完成的停止；本模块不会自动丢弃有效拍来强行停止。外部 `aresetn` 是另一个会终止传输、清流水线和总线状态的复位边界，不等同于正常 STOP。

未来 PS 接入的正常次序是：确认停止并按需要 RESTART；准备接收缓冲区及 DMA；START；请求停止后继续处理当前包，直到 STATUS=0；读取统计。单纯 STOP/START 不应重置 C 帧序号校验状态；显式重启需要与 DMA 停止、缓冲区所有权及 `fv_reset` 协调。本步没有把这些寄存器接入 `standalone_s2mm_draft`，不能只复位软件状态就宣称采集周期已重启。

## AXI4-Lite 实现范围

AW 和 W 各有一个保持寄存器，可任意先后到达；两个握手都已完成后才执行一次写入并产生 BVALID。B 响应未接受时不接收下一笔 AW/W。读路径独立，AR 握手时采样数据并产生 RVALID；R 响应未接受时不接收下一笔 AR。读写可并行，但每个方向至多一笔在途请求，没有追求每拍一笔的流水线总线吞吐。

读取计数器或状态时取得 AR 握手沿之前的值：不包含同沿新传输、停顿或寄存器写入的效果。B/R 反压期间响应保持；写命令不等待 BREADY 才生效，因此软件延迟接收响应不会重复执行命令。

握手与稳定性规则参照 AMD [PG101 AXI Protocol Checks](https://docs.amd.com/r/en-US/pg101-axi-protocol-checker/AXI-Protocol-Checks-and-Descriptions)：写响应必须晚于地址和数据握手；背压时响应/有效信号保持。本步使用自写检查器，没有运行厂商 AXI VIP 或声称完成全部协议认证。

## 2026-11-04 实际仿真

Icarus Verilog 13.0 编译及执行退出码均为 0，无编译警告；460 个仿真周期完成。

| 实测项目 | 数量 |
| --- | ---: |
| 写事务（AW/W/B 完整配对） | 23 |
| 读事务（AR/R 完整配对） | 46 |
| AW 先到 / W 先到 / 同拍到达 | 5 / 3 / 15 |
| B / R 反压周期 | 33 / 161 |
| 下一笔 AW / W / AR 等待周期 | 7 / 7 / 7 |
| 输出接受字 / 帧 | 70 / 10 |
| 输出停顿周期 | 89 |

这些是整个有限测试跨清计数、重启的累计覆盖量，不是末次寄存器读值或板端性能。

另用原入口 `run_sim.py --suite all --output results/axi_lite_regression` 实际复跑了三组 source 与三组 FIFO 测试，**6/6 通过**，包括原有回绕、满/空、复位、最终排空和数量守恒检查；[回归汇总](../results/axi_lite_regression/summary.json) 保留本次结果。既有检查未放宽。

[独立 testbench](../tb/tb_daq_axi_lite.sv) 只看公开接口。它由已接受字数推算期望序号、索引、TKEEP 和 TLAST，独立统计输出字/帧/停顿，并在 AR 握手时保存参考计数，与实际返回数据比较；不读取 DUT 内部寄存器。检查包括：

- 地址/数据分开到达、零 WSTRB、只写高字节、低字节和全字节写入、只读/非法/未对齐地址响应。
- B/R 反压与稳定性，在旧响应阻塞时提前提出下一笔请求，以及运行中的连续并行读写。
- 计数变化时保持一个读响应，验证返回值不会跟随实时计数变化。
- 被反压的第一字收到 STOP 后仍完成整帧；被反压的 TLAST 收到 STOP 后仍保持该拍并在接受后停止。
- 停止后的静默、清计数保留序号、重新开始连续序号、运行中清除/重启被拒绝、显式重启后重新输出帧 0。

证据：[汇总](../results/axi_lite/summary.json)、[编译日志](../results/axi_lite/compile.log)、[仿真日志](../results/axi_lite/simulation.log)、[总线握手 CSV](../results/axi_lite/axi_transactions.csv)、[流周期 CSV](../results/axi_lite/stream_cycles.csv)。流 CSV 中总线信号取采样沿前的值，`epoch_words/metric_*` 是该沿握手后更新的 testbench 参考量；参考量在已停止的清除/重启命令响应后重置。实际寄存器读值见总线 CSV 的 R 行。

## 复现和未验证项

从实验根目录执行，可更换输出目录保留当前证据：

```powershell
& 'E:\python.exe' .\scripts\run_axi_lite.py --output results/axi_lite_recheck
```

已有 Python/Icarus 的 Linux 环境可运行 `python scripts/run_axi_lite.py --output results/axi_lite_ci`；支持 `--iverilog` 指定现有工具。入口只编译并仿真，不安装工具或访问硬件。

该 wrapper 尚未加入既有 Vivado Tcl。完整 Vivado 中的接口推断/封装、地址分配、PS BSP、DMA/DDR、综合资源及板级时序均未由本步验证。计数器 32 位回绕、其他帧长/深度及运行中外部复位的总线事务中断未在这个新 TB 中专项测试；既有 source/FIFO 的其他配置测试仍保留，不用它们冒充新接口覆盖。
