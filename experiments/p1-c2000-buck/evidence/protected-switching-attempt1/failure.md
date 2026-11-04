# PWM 保护首轮测试接口错误

`protected-switching-tests.txt` 保存完整失败输出：10 项测试中 9 项通过，正常 PWM 回归测试调用 `existing_check_failures` 时发生 `TypeError: must be real number, not str`。

`compare_pi.py` 的旧检查器对输入表所有值调用 `math.isfinite`。新保护表增加了 `state`、`active_faults`、`latched_fault`、`clear_result` 字符串列，直接传入表导致错误。故障仿真及物理状态、实际电压、储能、恢复测试已经通过；不是功率级或保护判据失败。

本目录保存发生错误的测试、调用代码、检查器以及运行和测试日志。完整四工况仿真输出仍保存在 `simulation/protected_switching_results/`，本次修复不改仿真输出；没有为测试接口错误重复复制 CSV。

在相邻 `protected-switching-fix/` 隔离副本中，只将原 PWM 表的数字字段选出后传给原检查器。检查器、阈值、控制器、积分实现不改动；原有逐字段轨迹比较仍保留。先定向执行错误用例，再把修正后的测试复制回主实验并重跑全部测试。
