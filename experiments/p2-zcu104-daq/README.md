# P2：ZCU104 FPGA 数据采集学习项目

当前阶段：原厂代码已先行保存；第一小步新增了独立 AXI-Stream 数据发生器与 testbench，并通过 Icarus Verilog 13.0 的真实 RTL 仿真。尚未完成 ZCU104 工程适配、FIFO/DMA/DDR 集成或板端验证。

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
- 尚未创建 FIFO/DMA/DDR 块设计及 PS 侧改进工具。没有板端吞吐量、延迟或丢帧率测量结果。
- `E:\AMDDesignTools\2025.2` 中发现 Vivado Lab，未找到 xvlog/xelab/xsim 可执行文件；没有将 Lab Edition 称作可用的完整仿真工具链。本次实际用的是本目录 Icarus Verilog 13.0。
- PATH 中的 `E:\Scripts\python.exe` 报告缺少 `pyvenv.cfg`，实际使用正常的 `E:\python.exe`（3.14.4），未改动系统设置。首次 Python 下载请求发生 TLS EOF，改用 PowerShell 从 MSYS2 官方镜像成功取回；没有关闭 TLS 校验，记录见 [tool_setup.log](results/first_step/tool_setup.log)。

## 如何开始阅读

先阅读 [原始轮询示例](vendor/embeddedsw-xilinx_v2025.1/XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c)，依次跟踪初始化、禁用中断、cache flush、接收/发送提交、轮询及 cache invalidate 后的数据校验。API 含义可参照 [AMD AXI DMA 驱动文档](https://xilinx.github.io/embeddedsw.github.io/axidma/doc/html/api/index.html)；该文档网站可能随上游更新，本目录源码以 `xilinx_v2025.1` 为准。

查看本次原始文件清单，可在本目录执行：

```powershell
Import-Csv .\sources.csv | Format-Table upstream_path, bytes, result -AutoSize
```

## 下一小步

原厂源码仍保留在 `vendor/` 且未改动。后续可先接入一个 FIFO 做独立仿真，再结合完整 Vivado 工具与 ZCU104 硬件设计逐步验证 DMA、DDR 和 PS cache 一致性。本轮未执行上板、写卡或硬件重跑操作。
