# 连续物理闭环的隔离开发记录

新实现首先在本目录的 `work/` 副本开发与真实执行；原固定角、PI、采样保护及损耗预算代码保留作回归参照。本轮没有发生模拟或测试失败，不虚构失败案例。`work/` 是可再生隔离副本，不进入提交。

保留日志：

- `initial_switching_tests.log`：首先验证固定角物理等价，以及死区中断后节点状态持续，2 项通过。
- `initial_closed_loop.log`：原三组 PI 场景首次接入连续物理状态的实际结果。
- `initial_integration_tests.log`：8 项新增测试首次执行通过。
- `full_run.log`：16 个固定角各 100 周期回放、6 个完整工况和 55 项测试通过。
- `sample_turnon_tie_test.log`：进一步把故障采样放到高管开通的同一时刻，确认保护先行；同一测试中的死区中途子例也通过。

隔离完整运行命令为：

```powershell
& E:\python.exe -B -X utf8 .\run_continuous_control.py --source E:\UserData\Documents\ChatGPT\硬件\experiments\p4-dab\results_eps\comparisons.csv
```

工作目录为本目录下的 `work/`。完整工况证据从隔离输出复制至实验目录的 `results_continuous_control/`，保留元数据中的原始执行路径；最终测试日志另记实际测试命令。没有重新生成旧阶段结果，没有放宽物理阈值或保护条件，没有硬件操作。
