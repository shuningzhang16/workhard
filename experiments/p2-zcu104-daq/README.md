# P2：ZCU104 FPGA 数据采集学习项目

当前阶段：保存 AMD 官方原始代码，供首次 Git 提交及后续逐步改造使用。尚未完成 ZCU104 工程适配、编译、RTL 仿真或板端验证。

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

## 当前检查结果与限制

- 已实际下载 15 个上游文件，共 205,014 字节；每个文件长度与同版本 GitHub Contents API 返回值一致。结果记录于 `sources.csv`。这只是文件获取检查，不是功能验证。
- 官方示例要求 AXI DMA 的两个 AXI-Stream 方向之间存在硬件回环，并采用 Simple DMA 模式。其代码不是内部数据发生器，也不是单独可运行的电脑程序。
- 这里保存的是驱动源码和一个示例的子集，不包含完整 embeddedsw、Standalone BSP、生成的 `xparameters.h`、板级配置、链接脚本或 Vivado 硬件设计。`src/xaxidma_g.c` 不能当作已生成的 ZCU104 配置使用。
- 尚未创建 AXI-Stream 数据源、FIFO/DMA/DDR 块设计及 PS 侧改进工具，也没有运行编译、仿真或硬件测试。没有吞吐量、延迟或丢帧率测量结果。
- 工具盘点仅完成初查：PATH 未找到 Vivado/Vitis/iverilog/verilator，但发现 `E:\AMDDesignTools`，尚未确认其中的工具版本与可用性。PATH 中的 `python` 报告缺少 `pyvenv.cfg`，未改动系统设置。

## 如何开始阅读

先阅读 [原始轮询示例](vendor/embeddedsw-xilinx_v2025.1/XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c)，依次跟踪初始化、禁用中断、cache flush、接收/发送提交、轮询及 cache invalidate 后的数据校验。API 含义可参照 [AMD AXI DMA 驱动文档](https://xilinx.github.io/embeddedsw.github.io/axidma/doc/html/api/index.html)；该文档网站可能随上游更新，本目录源码以 `xilinx_v2025.1` 为准。

查看本次原始文件清单，可在本目录执行：

```powershell
Import-Csv .\sources.csv | Format-Table upstream_path, bytes, result -AutoSize
```

## 下一小步

先由协调聊天将本目录原始版本提交并上传到指定仓库，再新增独立的 AXI-Stream 数据源和 testbench，验证握手、TLAST 与背压。原厂源码保留在 `vendor/`，个人新增文件放在独立目录中，逐步提交。FIFO、DMA、DDR 和 PS cache 一致性留待后续有对应工程与验证条件时推进；本轮未执行任何上板、写卡或硬件重跑操作。
