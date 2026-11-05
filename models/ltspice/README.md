# LTspice 电路入口

两份独立低压教学网表可在 LTspice 中打开：buck_fixed.cir 保存固定占空比稳态窗口；buck_startup_loadstep.cir 保存零初态启动与 50 ms 时 4→2 Ω 负载变化。后者仍为开环固定占空比，不包含软件 PI、软启动或保护。参数来自本仓库教学模型，不是 TI 原厂电路。

电感显式使用 Rser=0，避免 LTspice 默认串联电阻改变理想电路。脉冲边沿为 1 ns，等效脉宽作了补偿以保持平均占空比；允许有符号电感电流。

**截至 2026-11-05，LTspice 尚未实际跑通，这两份网表没有 LTspice 数值验证结果。** 官方 26.1.1 已完成当前用户安装，官方 24.1.10 只在独立目录解包；两个版本的版本查询和批处理均启动超时，无日志或 RAW。见 [工具记录](../../verification/tooling/README.md)。

环境可正常启动后，将网表复制到新的本地输出目录，以官方命令 `LTspice.exe -b <网表绝对路径>` 执行；需要独立配置时使用 `-ini <路径>`。检查 .log 中的 .meas 结果与 .raw 波形，不能只凭文件存在宣布数值验证成功。

已真正运行的独立 SPICE 结果是 [P1 ngspice 对照](../../experiments/p1-c2000-buck/simulation/SPICE_COMPARISON.md) 和 [P4 ngspice 局部换流](../../experiments/p4-dab/results_deadtime_spice/RESULTS.md)。安装包、程序、库和个人配置不上传。

依据：[ADI 官方下载](https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html)、安装包的 Command Line Switches 与版本变更记录。
