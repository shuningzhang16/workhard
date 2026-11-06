# ZCU104 随仓板卡静态检查

日期：2026-11-06。实际运行结果：[static_check.log](static_check.log)，退出码 0；完整命令参数见 [commands.json](commands.json)。

本次读取已下载到仓库的官方 XilinxBoardStore 2025.2 原文件，并检查隔离暂存副本中的 create_project.tcl 修改。其余三个 Tcl 从当前仓库读取。没有加载、替代或模拟 Vivado 命令，也没有运行综合、实现、BSP 或硬件操作。

实际检查结果：

- 9 个原文件共 265463 字节，逐项大小与下载记录一致。此项不是重新联网的逐字节内容比对。
- 3 份许可通知均声明 Apache-2.0，另有 11358 字节的完整许可证。
- board.xml、part0_pins.xml、preset.xml 均可解析；目标为 xilinx.com:zcu104:part0:1.1 / xczu7ev-ffvc1156-2-e。
- part0_pins.xml、preset.xml、zcu104_board.jpeg 三个相对引用存在；board.xml 的全部 6 个 preset_proc 均在 preset.xml 定义，包含 zynq_ultra_ps_e_preset。
- 拟加入的固定目录按 P2 脚本位置可解析到仓库 vendor/xilinx-boardstore-2025.2/boards/Xilinx。
- Tcl 8.6.15 对 create_project.tcl、create_bd.tcl、export_addresses.tcl、build_offline.tcl 的 info complete 均为 True。该操作只检查文本是否完整，不执行 Tcl。

[review_board_vendor.py](review_board_vendor.py) 为此次只读检查脚本，不接入产品构建或 CI 门禁。合入文件后，从仓库根目录可用 Python 运行该文件，默认检查仓库内的真实 create_project.tcl；需新的日志文件时另存输出，不覆盖本次日志。

[changes.diff](changes.diff) 记录三处现有文件的最小修改；另新增根 vendor/xilinx-boardstore-2025.2/SOURCE.md 说明。最初一次准备工具调用发生 JavaScript 字符串解析错误，尚未启动 shell 或改变文件，记录于 [preparation_note.txt](preparation_note.txt)；修正后仅在暂存目录准备文件，最终静态检查成功。

限制：板卡文件是否被 Vivado catalog 接受、BD 接线/IP 参数、时序、匹配 A53 BSP 均未执行或证明。本次没有更改任何上游板卡文件、删除文件或运行 Git。
