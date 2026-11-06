# LTspice：已观察到启动隐私提示，电路仍未完成

2026-11-06，通过 Computer Use 的正常 `launch_app` 启动已安装的 LTspice 26 后，实际出现 **Anonymously Share LTspice Usage Data** 对话框。见[现场截图](gui26/startup_privacy_prompt.png)与[窗口和可访问性记录](gui26/observation.json)。画面中 Yes 为当前选项；这不是用户已经同意的证据。代理只读观察，没有选择 Yes/No、按 OK、关闭或输入按键，也没有改变隐私设置。该提示需由用户亲自处理。

这次明确定位了**正常 GUI 启动**尚未进入主窗口的原因；尚不能确认此前批处理超时也由同一个提示引起。

## LTspice 24 的新账户与全 ASCII 对照

根会话以 `win-ohfcgc0i6ia\administrator` 执行官方 24.1.10 提取程序，程序、网表和输出全部位于新的 ASCII 路径。最小电路仅为 1 V / 1 kΩ 的 `.op`。仍在 30 秒等待限额后被本次诊断脚本结束，完整诊断用时 34.914 秒，没有 `.log` 或 `.raw`；返回码 1 来自结束本次进程，不能写成求解器自行报告错误。

[原始摘要](v24_admin_ascii/summary.json)、[命令](v24_admin_ascii/command.json)、[超时进程记录](v24_admin_ascii/process_timeout.stdout.txt)均保留。PID 28956 的主窗口句柄为 0，超时时 CPU 时间为 0.5625 秒。此轮证明中文路径或旧 sandbox 账户不是足以解释全部失败的唯一条件，但没有确定批处理等待根因。

该轮 `Get-WinEvent` 同样未成功，原因是 `Microsoft.PowerShell.Diagnostics` 模块无法加载，见[错误原文](v24_admin_ascii/application_events.stderr.txt)。空事件输出不是“无事件”证据。本次 stage 不包含用户 INI、UUID、厂商程序或安装包。

## 下一次验证条件

此前批处理每次传入全新的空 `isolated.ini`，可能没有沿用用户已经确认的默认配置。这是待验证的解释，不能写成已确认根因。

待用户亲自完成默认启动提示后，在新的 ASCII 目录只隔离网表和输出，**不传 `-ini`**，先执行最小电路。代理不读取或修改用户 INI，也不代设匿名数据选项。只有最小电路实际完成并产生有效结果后，再运行 Buck。

[新的 Buck 脚本](run_buck_user_defaults.py)仅取消创建空 INI 和 `-ini` 参数；电路、两个有限场景、参考数据和原有 8 项判据均保持原样。它已通过 Python 静态语法检查，**尚未执行**。旧脚本与历史结果保留。当前没有 LTspice Buck 的成功结果，不能把窗口启动、脚本准备或既有 ngspice/Python 对照写成 LTspice 仿真完成。

官方命令参考：[ADI LTspice quick reference](https://www.analog.com/en/technical-articles/ltspice-keyboard-shortcuts.html)。安装附带官方帮助列出 `-version`；公开简表未列出不等于参数不受支持。
