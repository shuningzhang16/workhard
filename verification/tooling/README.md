# 工具运行状态：2026-11-06（含前阶段记录）

| 工具 | 实际事实 | 当前边界 |
| --- | --- | --- |
| C2000 cl2000 25.11.1 | 真实编译链接 F280049C RAM ELF，见 [固件证据](../../experiments/p1-c2000-buck/firmware/README.md) | 未执行目标指令或测量 ISR 时序 |
| Vivado/Vitis | 本机仅发现 Vivado Lab 2025.2，没有完整 Vivado/Vitis/xsct | 无器件实现、时序报告、XSA/BSP |
| AMD 安装入口 | xsetup.exe --help 要求提升；官方 bin/xsetup.bat --help 返回 Administrative permissions are not available | 没有修改安装器权限检查或完成增量安装 |
| LTspice 26 | 官方 MSI 26.1.1.2 签名 Valid，解包/当前用户安装 exit 0；EXE 26.1.1.0 | 批处理 45/180 秒超时，独立 INI 版本查询 30 秒超时，无日志或 RAW |
| LTspice 24 | 官方 24.1.10 MSI 签名 Valid，独立解包 exit 0；EXE 24.1.10.4 | 独立 INI 版本查询与 Buck 均 45 秒超时；[命令和结果](ltspice24-startup.json) |
| MATLAB/Simulink/PLECS/PSIM | 常见安装目录、卸载记录和 PATH 未发现可用运行时 | 不能报告这些工具已执行模型 |

LTspice 两个版本均无 stdout/stderr，也未暴露可操作窗口；24 版理想 Buck 显式设置 Rser=0。尚不能确认根因是配置、启动环境或特定软件缺陷。没有修改遥测/隐私选项来绕过首次运行流程。

后续按 [ADI 当前官方命令说明](https://www.analog.com/en/technical-articles/ltspice-keyboard-shortcuts.html) 使用 `-b -run`，在全新隔离目录执行仅包含 1 V 电源、1 kΩ 电阻及 `.op` 的最小网表，30 秒仍超时，无 `.log/.raw`。这次测试排除了 Buck 瞬态计算规模这个解释，但没有确定启动根因。[实际参数与结果](ltspice26-command-check.json)。先前使用的 `-version` 不在该官方标志表中，其超时不能单独证明工具故障；上述已记录批处理电路结果才是实际未完成的运行。随后通过 Computer Use 调用已安装程序的 `launch_app` 也返回 `computer-use request timed out: launch_app`；没有获得可操作 LTspice 窗口，之后进程查询及近 10 分钟应用错误/挂起事件查询均未返回 LTspice 条目。这不证明系统没有故障，仅说明这些入口没有提供根因证据。

下载来源：[ADI 当前版本](https://ltspice.analog.com/software/LTspice64.msi)、[ADI 24.1.10 官方归档](https://ltspice.analog.com/download/24.1.10/LTspice64.msi)。完整安装/诊断日志留在本地忽略目录；公开记录不含 INI、标识符、安装包或厂商程序。

继续使用真正运行成功的 Python、GCC、Icarus、Yosys、ngspice 和 C2000 编译器。以上工具缺口仍是未完成项，不能计为“只剩上板”。
