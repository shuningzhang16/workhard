# 控制功能整合后的本机复跑

2026-11-04，在仓库根目录实际执行：

```powershell
E:\python.exe -X utf8 scripts/check_offline.py
```

六项任务均退出 0：[汇总](summary.json)。本目录保存本次统一入口的完整日志副本，不修改各实验已提交的阶段数据。

| 任务 | 实际结果 | 日志 |
| --- | --- | --- |
| P1 Python | 10 项 Buck/保护/PWM 测试通过 | [p1_buck.log](p1_buck.log) |
| P1 主机 C | 严格编译与 ASan/UBSan 通过；26,004 点输出/状态一致；阈值边界检查通过 | [p1_host_c.log](p1_host_c.log) |
| P2 RTL | source/FIFO 六组通过 | [p2_rtl.log](p2_rtl.log) |
| P2 主机接收 | 真实 RTL 捕获、16 项帧校验与 13 项接收/恢复用例通过 | [p2_simple_s2mm.log](p2_simple_s2mm.log) |
| P2 AXI-Lite | 23 写、46 读、70 字/10 帧通过 | [p2_axi_lite.log](p2_axi_lite.log) |
| P4 Python | 33 项物理模型、调制、瞬态、保护、闭环及五点测试通过 | [p4_dab.log](p4_dab.log) |

`summary.json` 内的 `.runs/` 路径是本次本机原始输出位置；阶段数据在各实验目录，云端重跑另存 GitHub artifacts。Yosys 的两项综合网表重放独立执行并保留在 [stream](../yosys-stream/README.md) 与 [控制 wrapper](../yosys-control/README.md) 中。SPICE 对照仍以 P1 对应阶段报告为准。

运行环境为 Windows Python 3.14.4、Icarus 13.0 和 WSL Ubuntu 22.04/GCC 11.4。以上均为离线执行，未连接或写入硬件，不证明 MCU ISR 时序、Vivado 器件时序、DMA/DDR 或器件安全。
