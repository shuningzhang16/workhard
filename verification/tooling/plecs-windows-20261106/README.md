# PLECS 原生 Windows 文件准备与界面阻碍

2026-11-06，用户恢复 P4 后，旧会话和新会话均复现 WSLg 界面问题：鼠标菜单可响应，但画布单字母输入没有打开元件搜索；另有请求忙和截图串帧。新会话看到不属于目标窗口的图像时没有向该内容输入，重新激活目标后再观察。随后工具明确报告物理 Escape 用户停止，全部 GUI 立即停止。未创建新模型元件或取得 PLECS 正反向结果，见[观察记录](gui_observation.json)。

作为具体修复准备，已从[官方 5.0.7 Windows 下载链接](https://www.plexim.com/sites/default/files/packages/plecs-standalone-5-0-7_win64.exe)取得 389796880 字节安装包。安装器和恢复出的 PLECS.exe 均为 Plexim GmbH 的有效 Authenticode 签名，主程序产品版本 5.0.7。见[下载记录](download.json)、[签名观察](signatures.json)。

只做文件准备，没有运行安装器、注册组件、接受账户/许可条款或启动原生应用：先用本地解压的 Ubuntu p7zip 读取 PE 中嵌入的 MSI/CAB，Windows Installer COM 仅以只读模式读取 Directory/Component/File 表。首次 WSL 直接解压在 120 秒限额结束，2637 个部分文件保持原样。随后在全新目录使用 Windows 自带 expand 解开 CAB，退出 0，共 7069 文件；按 MSI 目录映射复制到另一个全新目录，恢复 867090412 字节文件。所有旧包、日志和部分输出均保留，没有删除文件。

主程序准备位置：

~~~text
E:\codex_plecs_runs\windows_5_0_7_20261106_184319\AppData\Plexim\PLECS 5.0 (64 bit)\PLECS.exe
~~~

[恢复结果](native_files_summary.json)。此步骤不证明该解包目录可免安装正常运行，也没有解决或绕过 Demo 的文件签名、保存和导出限制。下一次明确恢复 GUI 后，先从原生 Windows 程序验证正常 Demo 启动与画布输入，再继续固定双源正反向模型；原来的 Linux 官方 DAB 0.8 s 结果保留。

已完成的独立[LTspice 正反向 R-L 仿真](../../../experiments/p4-dab/spice_rl/README.md)与 PLECS 界面状态分开记账。第三方安装包及程序均留在本地，不上传为个人源码。
