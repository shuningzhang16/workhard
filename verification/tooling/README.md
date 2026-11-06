# 工具运行状态：2026-11-06（含前阶段记录）

| 工具 | 实际事实 | 当前边界 |
| --- | --- | --- |
| C2000 cl2000 25.11.1 | 测量区间清除接口已重新编译链接；C ADC 换算在主机定向测试中执行，见 [新证据](../../experiments/p1-c2000-buck/host_c/CLEAR_MEASUREMENTS.md) | 目标 ADC 寄存器/ISR 未执行，输出禁止不变；零码信息缺口未被硬件验证补足 |
| Vivado/Vitis 2025.2 | 本机仍仅发现 Vivado Lab；已准备完整离线构建/报告/无 bitstream XSA 入口及匹配 A53 BSP 路径，见 [新版工具链记录](../../experiments/p2-zcu104-daq/vivado/toolchain_2025_2.md) | 仅完成 Tcl 文本与目录保留检查；无实际 BD、器件实现、时序、XSA 或 A53 BSP 编译结果 |
| AMD 安装与下载 | 本轮独立后台浏览器已从官方 2025.2 Linux 安装包链接到达真实 AMD 登录表单；未输入或提交凭据，见[新观察](amd-browser-20261106/README.md) | 尚无已认证下载和完整安装；不代表现有 Edge 的登录状态。WSL 虚拟余量不等于 E 盘物理空间，真实组件占用待安装摘要 |
| LTspice 26 | 已正常启动 GUI，实际停在匿名使用数据隐私选择框，需由用户亲自处理；见[新现场证据](ltspice-gui-and-v24-20261106/README.md) | 尚无电路结果；之前全新 INI 批处理超时与该提示是否同因仍待验证；后续使用用户默认配置，不传 `-ini` |
| LTspice 24 | 官方 24.1.10 MSI 签名 Valid，独立解包 exit 0；EXE 24.1.10.4 | 独立 INI 版本查询与 Buck 均 45 秒超时；[命令和结果](ltspice24-startup.json) |
| PLECS Standalone 5.0.7 | Demo 已实际完成官方签名 DAB 的 0.8 s 运行，取得 1→2 kW 负载阶跃波形及结束窗口，见[平台状态](../../experiments/p4-dab/plecs/README.md) | 原例不是固定双母线反向实验；自建文件仍被签名限制拒绝；低压正反向数值对照待完成，未导出原始数组 |
| MATLAB/Simulink/PSIM | 本机仍未发现可用运行时；[Simulink 脚本](../../docs/SIMULINK.md) 已准备，P4 另记录合法平台入口 | 未执行模型；PLECS 的独立解析参考值也不能替代这些工具的输出 |

此前 LTspice 两个版本的批处理均无 stdout/stderr，也未暴露可操作窗口；24 版理想 Buck 显式设置 Rser=0。尚不能确认根因是配置、启动环境或特定软件缺陷。没有修改遥测/隐私选项来绕过首次运行流程。

后续按 [ADI 当前官方命令说明](https://www.analog.com/en/technical-articles/ltspice-keyboard-shortcuts.html) 使用 `-b -run`，在全新隔离目录执行仅包含 1 V 电源、1 kΩ 电阻及 `.op` 的最小网表，30 秒仍超时，无 `.log/.raw`。这次测试排除了 Buck 瞬态计算规模这个解释，但没有确定启动根因。[实际参数与结果](ltspice26-command-check.json)。先前使用的 `-version` 不在该官方标志表中，其超时不能单独证明工具故障；上述已记录批处理电路结果才是实际未完成的运行。随后通过 Computer Use 调用已安装程序的 `launch_app` 也返回 `computer-use request timed out: launch_app`；没有获得可操作 LTspice 窗口，之后进程查询及近 10 分钟应用错误/挂起事件查询均未返回 LTspice 条目。这不证明系统没有故障，仅说明这些入口没有提供根因证据。

下载来源：[ADI 当前版本](https://ltspice.analog.com/software/LTspice64.msi)、[ADI 24.1.10 官方归档](https://ltspice.analog.com/download/24.1.10/LTspice64.msi)。完整安装/诊断日志留在本地忽略目录；公开记录不含 INI、标识符、安装包或厂商程序。

当前阻碍按入口集中记录：P1 是待用户亲自处理 LTspice 启动隐私提示及真实前端测量证据缺失；P2 是完整 2025.2 工具获取和匹配 BSP 尚未构建；P4 官方原例已运行，固定双电源正反向对照仍待完成，Demo 的文件签名限制仍在，MATLAB/Simulink 也没有运行结果。启动窗口、生成输入或文本检查均不能计为厂商平台仿真成功。

继续使用真正运行成功的 Python、GCC、Icarus、Yosys、ngspice 和 C2000 编译器。三个实验均未上板；以上离线工具缺口也仍未完成，不能计为“只剩上板”。

2026-11-06 权限切换后，根会话为 administrator（Windows token 未提权），WSL 已可正常访问；旧子代理仍受旧权限约束，其拒绝记录不能代表根会话状态。新 ASCII 路径的 LTspice 最小电路仍30秒无输出，进程线程等待的完整记录见 [本轮诊断](ltspice-admin-ascii-20261106/DIAGNOSIS.md)。原 Get-WinEvent 查询失败，不是“无事件”；另有成功的有限范围 wevtutil 查询。安装内官方帮助明确列出 `-version`，公开简表未列出不等于该参数不受支持。

前一轮 PLECS 已进入 Demo，但只允许新建模型或打开官方签名示例；自行生成的模型被实际拒绝。没有绕过签名、导出限制或重新标注解析值为仿真结果。共享界面工具在后续 Edge 操作时因无法可靠识别当前 URL 而强制结束本轮电脑操作，AMD下载页面未打开、登录状态未确认、官方DAB仍未载入。全部GUI随后停止；下一轮需从明确可识别的应用/网页状态恢复。

2026-11-06 本轮用户恢复后，PLECS GUI 已继续，官方签名 DAB 已完成 0.8 s 仿真。LTspice 正常启动的隐私提示也已取得现场证据；代理未选择、确认或修改任何隐私设置。上述早期工具停止、无窗口和未运行记录保留为历史，当前状态以表格及最新证据为准。
