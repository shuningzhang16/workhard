# 瞬态恢复失败与隔离修复记录

日期：2026-11-04。第一次运行命令为 `E:\python.exe -B run_transient_demo.py`。

1. 四个工况 CSV 已生成。测试子进程的失败堆栈包含中文路径，Windows 默认编码与父进程 UTF-8 解码不一致，先触发解码错误，随后日志拼接出现 TypeError；见 `first_run_failure.log`。
2. 保留原始代码及完整失败数据，在 `work/` 隔离副本中以 `-X utf8` 重现测试。`tests_before_fix.log` 显示真实失败：清除后直接请求 −30°，即使控制器按 6°/周期变化，瞬态仍触发 1.6 A 过流保护，导致第二次锁存。`before_fix_events.csv` 保留这次事件；第二次检测电流为 1.648811 A。
3. 最小修复：测试子进程显式使用 UTF-8；成功恢复演示的请求端改用 2°/周期反向斜坡；报告只统计首次连续锁存区间的能量，避免跨恢复区间相加。没有改变电感状态方程、1.6 A 阈值或原测试容差。
4. 增加回归测试，确认原来的快速恢复请求仍会再次锁存。隔离副本的完整 19 项测试通过，记录为 `tests_after_fix.log`。随后仅合回三个新增 Python 文件，并重新运行成功版本，最终证据在 `../../results_transient/`。

`original/`、`failed_run/`、`work/`、`validated/` 为本机保留的原始快照、失败完整数据、隔离修复副本及验证输出；它们由上级 `.gitignore` 排除，避免重复提交源码和大份 CSV。简短失败日志、事件、测试输出及本记录随项目保留。

重现快速恢复反例：在实验根目录运行 `E:\python.exe -B -X utf8 -m unittest -v test_dab_transient.TestTransient.test_fast_recovery_still_retrips_without_relaxing_threshold`。该测试以“再次锁存”为正确结果。
