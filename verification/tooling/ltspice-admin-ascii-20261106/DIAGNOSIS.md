# LTspice 26 启动等待：管理员与 ASCII 路径复核

2026-11-06 16:48（本地）由根代理的 administrator 会话执行。用户属于 Administrator，根代理报告当前 token 未提权。旧子代理仍是 CodexSandboxOffline，未把旧子代理的文件写入拒绝误认为新会话权限失败。

原始证据：`E:\codex_ltspice_runs\admin_ascii_20261106_164830_750328`。官方已签名 LTspice 26.1.1.0，新的 ASCII 输出目录，1 V / 1 kΩ 的 `.op`，官方 `-b -run -ascii -ini` 参数，全新 INI。没有改隐私/安全设置。

30 秒仍无 `.log` / `.raw`。进程 PID 47036 的 CPU 时间在 5 秒和 30 秒均为 0.21875 秒，WorkingSet 均为 20,144,128 字节，MainWindowHandle 为 0。主线程 WaitReason 为 UserRequest，另三线程为 EventPairLow；未看到子进程。只终止本次创建的 PID，随后返回码为 1；这不是求解器自行报告的电路错误码。程序只向新 INI 增加 UUID（不纳入报告）。

这些现象支持“进程已启动但处于等待、尚无电路求解输出”，不足以区分等待对象、网络、初始提示或其他原因，不能声称已找到根因。

原 probe 的 `Get-WinEvent` 未成功：Microsoft.PowerShell.Diagnostics 模块加载失败，错误见 `probe_application_events.stderr.txt`。其空 stdout **不是无事件证据**。后续只读 `wevtutil` 查询的准确命令、执行身份、时间、返回码和原始 stdout/stderr 已独立保存。若退出 0 且输出为空，只表示指定时间范围的 Application 错误/警告记录未返回，不代表所有系统日志均无问题。

安装附带的官方 `LTspiceHelp/Third_Party_AI_Tools.htm` 说明 26.1 有首次启动第三方 AI 配置提示；这是下一次 GUI 检查的候选线索，目前没有看到实际对话框，不能确认它导致本次等待。用户已重新授权 GUI，按根代理安排等待 P4、P2 使用完后检查。不会为跳过提示修改设置，也不重复同一最小超时。

尚未运行 Buck。已准备 `ltspice_buck_20261106_165000.py` 并完成 Python 静态语法检查：保留原网表，在新 ASCII 目录将电感显式 `Rser=0` 对齐理想参考，再实际执行启动和稳态两个有限场景，保存 ASCII raw/log/CSV，与已有 ngspice/Python 有限窗口比较，沿用原 8 项判据。它尚未实际执行，不能当作 LTspice 验证结果。

官方参数来源：[ADI LTspice 26 quick reference](https://www.analog.com/en/technical-articles/ltspice-keyboard-shortcuts.html)。电感默认 1 mΩ 与显式 `Rser=0` 参见安装附带的 `LTspiceHelp/inductormodels.htm` 及 [ADI reference](https://analogdevicesinc.github.io/ltspice-reference/ai_ref/DEVICE-MODELS-GUIDE.html)。

补充核对：上述官方 AI 配置提示的触发条件明确限定为 normal (GUI) mode。因此该说明只支持下一步观察普通启动，不能据此解释本次 -b 批处理等待。

参数文档更正：公开 quick-reference 未列出 -version，但已安装官方 26 帮助 commandlineswitches.htm 明确列出 -version / Print LTspice version.，本目录已保存该帮助原文件。因此历史说明若写成“-version 不是官方参数”需更正为“所查 quick-reference 未列出”；本地帮助支持该参数，但没有以此重复任何运行。
