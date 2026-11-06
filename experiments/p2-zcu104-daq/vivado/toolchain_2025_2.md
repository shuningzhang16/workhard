# 2025.2 完整工具链续接记录

核对时间：2026-11-06。当前没有实际 P2 Vivado BD、综合、实现、时序报告或匹配 A53 BSP 编译结果。新增的 build_offline.tcl 是待执行入口，Tcl 文本检查不能代替这些结果。

本次已实际通过 4 个 Tcl 文件的 info complete 文本检查，以及两个入口对已有输出目录的拒绝检查。证据：[文本检查](../results/toolchain_preparation_20261106_102605_858412/tcl_text_check.log)、[已有目录检查](../results/toolchain_preparation_20261106_102605_858412/existing_directory_check.log)。这些检查没有执行 Vivado 命令。

随后最小修复两个命令问题：PowerShell 入口显式检查 Vivado 的 `$LASTEXITCODE`，非零则抛错并保留输出；`check_tcl_text.py` 默认生成独立新目录，显式指定 `--output` 时也拒绝已有日志。已实际验证两次默认输出目录不同、已有测试日志与历史日志的内容及修改时间不变，以及用无文件副作用的 Python `exit(7)` 替换原生命令后 PowerShell 返回非零。见 [定向验证](../results/toolchain_command_fix_20261106_103318_119885/summary.json)。首轮测试程序误解码中文路径的记录保留，只修正测试子进程 UTF-8 设置后复验；未运行 Vivado、删除文件或改变文档原换行风格。

## 已核实的工具、空间与许可

| 项目 | 实际观察 |
| --- | --- |
| 已有 Windows 工具 | E:\AMDDesignTools\2025.2\Vivado_Lab；已查安装目录/PATH 未发现完整 Vivado/Vitis |
| Windows 安装入口 | 已有 .xinstall\2025.2\xsetup.exe 的启动要求管理员；未绕过 UAC 或改用内部启动器规避检查 |
| Linux 用户环境 | WSL2 Ubuntu-22.04，Ubuntu 22.04.5 LTS，x86_64，普通用户 UID 1000 |
| WSL 存储 | 注册路径 E:\WSL\Ubuntu-22.04\ext4.vhdx；它与本项目共用 E 盘 |
| 物理空闲空间 | 首次 C 24.38 / D 53.85 / E 100.33 GiB；10:17 复查 C 24.24 / D 53.85 / E 99.15 GiB |
| WSL df | 根分区显示 645 GiB 可用是虚拟容量，不能代替 E 盘物理空间 |
| 已查缓存 | 项目 .tools、P2 .tools 和 Downloads 的 AMD/Vivado/Vitis 安装包文件名，没有发现完整 Linux 工具缓存 |

AMD [2025.2 支持器件表](https://docs.amd.com/r/2025.2-English/ug973-vivado-release-notes-install-license/Supported-Devices)列出 XCZU7EV；[许可 FAQ](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/licensing-faq.html)说明 2025.2 及以前 ML Standard 无需 FLEX 许可证。应选 **Vivado ML Standard 2025.2**，不把 2026.1 的新许可规则套到此版本。

[2025.2 支持操作系统](https://docs.amd.com/r/2025.2-English/ug973-vivado-release-notes-install-license/Supported-Operating-Systems)包含 Ubuntu 22.04.5 x86_64，但未明确列出 WSL；因此 WSL 是本机可尝试的执行环境，不能写成 AMD 已支持的 WSL 配置。[安装线缆驱动说明](https://docs.amd.com/r/2025.2-English/ug973-vivado-release-notes-install-license/Installing-Cable-Drivers)明确 Linux 常规工具安装可不用 root/sudo；线缆驱动需要管理员，离线构建不需要安装它。

## 精确官方入口与当前卡点

下列文件名来自 [AMD 2025.2 官方下载页](https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2025-2.html)的实际按钮。大小为该页显示值，不是已完成下载。

| 用途 | 文件与大小 |
| --- | --- |
| 推荐的选择性安装入口 | [Linux Web Installer](https://account.amd.com/en/forms/downloads/xef.html?filename=FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_1114_2157_Lin64.bin)，FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_1114_2157_Lin64.bin，346.7 MB |
| 可单独取得嵌入式工具 | [Vitis Embedded Linux](https://account.amd.com/en/forms/downloads/xef.html?filename=Vitis_Embedded_Lin_2025.2_1114_2157_1.tar)，Vitis_Embedded_Lin_2025.2_1114_2157_1.tar，7.93 GB |
| 本机未选用 | 全 OS Unified SFD 为 95.68 GB；接近 E 盘全部余量，还需要解包及安装空间 |

两条实际下载链接在网页抓取中都重定向到 account.amd.com/my.logout.php3?errorcode=19，页面报告 F5 无法建立会话。随后尝试通过现有 Edge 新标签只读确认会话，Computer Use 返回 Computer Use app approval timed out，未取得浏览器登录状态。这不能证明用户没有 AMD 账户；它说明本次没有可用的已认证下载通道。

[官方安装流程](https://docs.amd.com/r/2025.2-English/ug973-vivado-release-notes-install-license/Run-the-Installation-File)要求 AMD 账户登录。批处理也须先[获取认证 token](https://docs.amd.com/r/2025.2-English/ug973-vivado-release-notes-install-license/Acquire-Authentication-Token)，有效期 7 天。不要把账户/密码/token 提交到仓库，也不要从浏览器或其他配置文件提取凭据。

最小安装组件为 Vivado ML Standard、Zynq UltraScale+ MPSoC（XCZU7EV）及 Vitis Embedded 的 A53 Standalone 开发工具。ZCU104 官方 1.1 板卡目录已从 XilinxBoardStore 的 2025.2 分支保存到根目录 vendor/xilinx-boardstore-2025.2；工程入口固定按仓库相对路径加入 board.repoPaths，无需另行手工配置板卡 catalog。见[原始文件来源与许可证](../../../vendor/xilinx-boardstore-2025.2/SOURCE.md)及[本次 XML/文本检查](../results/board_vendor_20261106_175304_840/README.md)。该检查没有调用 Vivado，也不证明 preset 已被工具接受。精确下载/安装占用须由真实安装摘要给出，目前不估造数字。现有 Lab、非本板 XSA、2025.1 驱动源码都不替代这些组件。

用户当前要求不删除任何文件；所有续接应使用新目录，不清理腾空间，不覆盖旧工程。官方提供的保留解包方式是：

~~~bash
sh FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_1114_2157_Lin64.bin \
  --keep --noexec --target /path/to/NEW_client_directory
~~~

此命令依据 [Extract Web Installer Batch Mode Client](https://docs.amd.com/r/2025.2-English/ug973-vivado-release-notes-install-license/Extract-Web-Installer-Batch-Mode-Client)。只在真实文件已经由官方渠道下载并核验之后执行。--keep 只控制自解压阶段，不保证后续安装器或 Vivado 内部完全不删除临时文件；在已知会触发 cleanup 时，不能直接运行与当前限制冲突的步骤。没有为本次任务启动完整 Linux 安装或硬件操作。

## 工具到位后的真实构建入口

create_project.tcl 现在可接受调用方预设的 build_dir，已存在的输出目录会被拒绝。build_offline.tcl 复用现有工程定义，按顺序执行 BD/输出生成、综合、布局布线到 route_design，保存综合及实现状态、资源、setup/hold、未约束路径、时钟、DRC、routed DCP 与不含 bitstream 的 XSA。

在已核对工具内部文件行为符合当前授权之后，从 P2 实验根目录运行，每次换一个不存在的目录：

~~~bash
P2_ROOT="$PWD"
RUN_DIR="$P2_ROOT/build/toolchain_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$P2_ROOT/build" || exit 1
mkdir "$RUN_DIR" || exit 1
cd "$RUN_DIR" || exit 1
vivado -mode batch -source "$P2_ROOT/vivado/build_offline.tcl" \
  -log "$RUN_DIR/vivado.log" -journal "$RUN_DIR/vivado.jou" \
  -tclargs "$RUN_DIR/project" 2
~~~

入口不调用 reset、删除、强制覆盖、bitstream 或硬件命令；保留失败目录。Vivado 的成功退出只表示流程完成，仍应审阅 reports/route_timing.rpt 中 WNS/TNS、WHS/THS、未约束路径、时钟与 route_drc.rpt；不能据 XSA 文件存在就宣称 100 MHz 已通过。命令依据：[2025.2 时序报告](https://docs.amd.com/r/2025.2-English/ug835-vivado-tcl-commands/report_timing_summary)、[2025.2 XSA 导出](https://docs.amd.com/r/2025.2-English/ug835-vivado-tcl-commands/write_hw_platform)。

## 匹配 A53 BSP 的续接

必须使用本次成功 BD 生成的 project/daq_zcu104.xsa，并用同版 Vitis Embedded 2025.2 在全新 workspace 创建 psu_cortexa53_0 / standalone / 64-bit 平台，然后实际 build BSP。API 依据：[AMD 2025.2 Vitis scripting tutorial](https://github.com/Xilinx/Vitis-Tutorials/blob/2025.2/Embedded_Software/Feature_Tutorials/04-vitis_scripting_flows/README.md)。

随后编译本项目 frame_validator.c、simple_s2mm.c、daq_session.c、daq_queue.c 和 standalone_s2mm_draft.c，使用生成 BSP 的头文件、驱动和编译定义，不能混用 vendor/embeddedsw-xilinx_v2025.1。要保存真实 compiler/version、完整命令、输出/错误和产物。编译成功仍不代表 DDR 缓冲区映射、cache 交接或 DMA 运行通过；可执行板端应用还需要真实 linker/memory 配置和入口。此次没有生成虚构 xparameters.h、假 BSP、假 ELF 或 ARM 编译通过记录。
