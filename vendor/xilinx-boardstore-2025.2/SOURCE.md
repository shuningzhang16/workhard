# ZCU104 板卡文件来源

此目录保存 AMD 官方 [Xilinx/XilinxBoardStore 的 2025.2 分支](https://github.com/Xilinx/XilinxBoardStore/tree/2025.2/boards/Xilinx/zcu104/1.1) 中的完整 boards/Xilinx/zcu104/1.1 小目录，以及上游根目录许可通知。下载日期：2026-11-06。没有下载其他板卡或完整工具安装包。

上游原文件保留原路径、内容和版权声明；[download_record.json](download_record.json) 记录逐文件 URL 和下载字节数。版本以官方分支 2025.2、板卡 1.1 标识。

| 原始相对路径 | 字节数 |
| --- | ---: |
| boards/Xilinx/zcu104/1.1/LICENSE | 751 |
| boards/Xilinx/zcu104/1.1/board.xml | 37979 |
| boards/Xilinx/zcu104/1.1/changelog.txt | 211 |
| boards/Xilinx/zcu104/1.1/part0_pins.xml | 13989 |
| boards/Xilinx/zcu104/1.1/preset.xml | 25812 |
| boards/Xilinx/zcu104/1.1/xitem.json | 841 |
| boards/Xilinx/zcu104/1.1/zcu104_board.jpeg | 184442 |
| LICENSE | 719 |
| LICENSE.md | 719 |

板卡目录的 [LICENSE](boards/Xilinx/zcu104/1.1/LICENSE) 为 Copyright (C) 2023, Advanced Micro Devices, Inc；根 [LICENSE](LICENSE) 和 [LICENSE.md](LICENSE.md) 为 Copyright (C) 2019, Xilinx Inc。它们均声明 Apache License 2.0。另附从 [Apache 官方文本](https://www.apache.org/licenses/LICENSE-2.0.txt) 下载的完整 [APACHE-2.0.txt](APACHE-2.0.txt)。SOURCE.md 和下载记录是本项目新增的来源说明，不是上游文件。

此目录可供 P2 工程通过 board.repoPaths 使用。官方配置依据：[AMD UG895](https://docs.amd.com/r/2025.1-English/ug895-vivado-system-level-design-entry/Elements-of-the-Platform-Board-Flow)。工程入口的集成是单独的代码改动。

已做的只读静态核对覆盖 XML 可解析、板卡/器件/版本一致、相对文件存在，以及 board.xml 引用的全部 6 个 preset 名称在 preset.xml 中可找到。没有运行 Vivado、加载 catalog、执行 BD/综合/实现，或编译匹配 A53 BSP；随仓文件不替代完整工具和器件支持。
