# 工具运行状态：2026-11-06（含前阶段记录）

| 工具 | 实际事实 | 当前边界 |
| --- | --- | --- |
| C2000 cl2000 25.11.1 | 测量区间清除接口已重新编译链接；C ADC 换算在主机定向测试中执行，见 [新证据](../../experiments/p1-c2000-buck/host_c/CLEAR_MEASUREMENTS.md) | 目标 ADC 寄存器/ISR 未执行，输出禁止不变；零码信息缺口未被硬件验证补足 |
| Vivado/Vitis 2025.2 | 本机仍仅发现 Vivado Lab；已准备完整离线构建/报告/无 bitstream XSA 入口及匹配 A53 BSP 路径，见 [新版工具链记录](../../experiments/p2-zcu104-daq/vivado/toolchain_2025_2.md) | 仅完成 Tcl 文本与目录保留检查；无实际 BD、器件实现、时序、XSA 或 A53 BSP 编译结果 |
| AMD 安装与下载 | Windows 安装入口要求管理员；Linux 官方 2025.2 安装入口已核实，但本次下载重定向到 F5 会话错误，Edge 应用审批超时，未取得认证通道 | 未绕过权限或会话检查；WSL 虚拟余量不等于 E 盘物理空间，真实组件占用尚待安装摘要；未完成完整安装 |
| LTspice 26 | 官方 MSI 26.1.1.2 签名 Valid，解包/当前用户安装 exit 0；EXE 26.1.1.0 | 批处理 45/180 秒超时，独立 INI 版本查询 30 秒超时，无日志或 RAW |
| LTspice 24 | 官方 24.1.10 MSI 签名 Valid，独立解包 exit 0；EXE 24.1.10.4 | 独立 INI 版本查询与 Buck 均 45 秒超时；[命令和结果](ltspice24-startup.json) |
| PLECS Standalone 5.0.7 | 官方 Linux 包已解压并启动，已出现 PLECS 窗口；独立原生正/反向模型输入已准备，见 [平台状态](../../experiments/p4-dab/plecs/README.md) | 应用操作审批超时；尚未进入 Demo、解析/编译模型或运行仿真，没有 PLECS 波形/数值结果 |
| MATLAB/Simulink/PSIM | 本机仍未发现可用运行时；[Simulink 脚本](../../docs/SIMULINK.md) 已准备，P4 另记录合法平台入口 | 未执行模型；PLECS 的独立解析参考值也不能替代这些工具的输出 |

LTspice 两个版本均无 stdout/stderr，也未暴露可操作窗口；24 版理想 Buck 显式设置 Rser=0。尚不能确认根因是配置、启动环境或特定软件缺陷。没有修改遥测/隐私选项来绕过首次运行流程。

后续按 [ADI 当前官方命令说明](https://www.analog.com/en/technical-articles/ltspice-keyboard-shortcuts.html) 使用 `-b -run`，在全新隔离目录执行仅包含 1 V 电源、1 kΩ 电阻及 `.op` 的最小网表，30 秒仍超时，无 `.log/.raw`。这次测试排除了 Buck 瞬态计算规模这个解释，但没有确定启动根因。[实际参数与结果](ltspice26-command-check.json)。先前使用的 `-version` 不在该官方标志表中，其超时不能单独证明工具故障；上述已记录批处理电路结果才是实际未完成的运行。随后通过 Computer Use 调用已安装程序的 `launch_app` 也返回 `computer-use request timed out: launch_app`；没有获得可操作 LTspice 窗口，之后进程查询及近 10 分钟应用错误/挂起事件查询均未返回 LTspice 条目。这不证明系统没有故障，仅说明这些入口没有提供根因证据。

下载来源：[ADI 当前版本](https://ltspice.analog.com/software/LTspice64.msi)、[ADI 24.1.10 官方归档](https://ltspice.analog.com/download/24.1.10/LTspice64.msi)。完整安装/诊断日志留在本地忽略目录；公开记录不含 INI、标识符、安装包或厂商程序。

当前阻碍按入口集中记录：P1 是 LTspice 启动未完成及真实前端测量证据缺失；P2 是完整 2025.2 工具获取和匹配 BSP 尚未构建；P4 是 PLECS 应用审批超时、原生模型未执行，MATLAB/Simulink 也没有运行结果。启动窗口、生成输入或文本检查均不能计为厂商平台仿真成功。

继续使用真正运行成功的 Python、GCC、Icarus、Yosys、ngspice 和 C2000 编译器。三个实验均未上板；以上离线工具缺口也仍未完成，不能计为“只剩上板”。
