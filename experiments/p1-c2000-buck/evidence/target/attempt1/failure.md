# 首次真实目标链接与隔离修复

2026-11-05，四个源文件均经 cl2000 25.11.1.LTS 实际编译通过；链接器因 `--emit_warnings_as_errors` 将 10063 提示提升为错误，退出 1。它指出显式入口 `code_start` 不同于默认 `_c_int00`，并非未解析符号、RAM 溢出或 C 语法问题。

已直接检查官方 `device_support/f28004x/common/source/f28004x_codestartbranch.asm`：保留的 `codestart` 段位于 RAM 链接脚本 BEGIN 地址 0，入口 `code_start` 跳到禁止看门狗的启动序列，随后用 `LB _c_int00` 进入 C 运行时。没有绕过 C 初始化。选择 `code_start` 是本 RAM 工程的有意启动方式；官方 TI Buck 项目元数据也使用此入口，并单独抑制 10063。

本目录保存失败时的新增源码、构建脚本、完整命令和输出。隔离验证只修改链接命令，新增 `--diag_remark=10063`，输出写入 `.tools/target-fix/`；仍使用实际 cl2000 目标对象、官方 DriverLib 与 RTS，退出 0，详见相邻 `isolated-link-fix.json`。

随后主构建针对 10063 使用 remark，并以 `--issue_remarks` 保留可见诊断。所有其他警告仍由 `--emit_warnings_as_errors` 处理。编译精度、控制器源码、保护阈值、Trip 锁存与 GPIO 禁用策略没有改变。本例的 10063 是已核对启动路径的入口提示，不作为上板安全证明。
