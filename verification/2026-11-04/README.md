# 统一离线检查的实际运行

2026-11-04 15:53（Asia/Shanghai）在仓库根目录执行 `E:\python.exe scripts/check_offline.py`，四个检查进程均以 0 退出：

| 检查 | 实际结果 | 原始输出 |
| --- | --- | --- |
| Buck | 8 项 Python 测试通过 | [p1_buck.log](p1_buck.log) |
| 数据源与 FIFO | 帧长 1/7/16、FIFO 深度 1/3/16 六组 RTL 仿真通过 | [p2_rtl.log](p2_rtl.log) |
| 顶层 RTL 与 C | 84 个真实 RTL 字；16 项 C 故障测试通过 ASan/UBSan | [p2_frame_validator.log](p2_frame_validator.log) |
| DAB | SPS、EPS、瞬态、换流极性共 25 项测试通过 | [p4_dab.log](p4_dab.log) |

[summary.json](summary.json) 与日志均为本次运行输出的未修改副本。文件中的 `.runs/` 路径指向本机保留的完整运行目录，未重复上传每轮仿真波形；各实验已提交的阶段结果提供对应原始数据。此轮未执行 SPICE 或 Vivado 构建，未操作硬件。SPICE 独立对照另见 P1 的阶段记录。

新机器可用 `python -X utf8 scripts/check_offline.py` 生成自己的记录。所需工具及实际验证边界见仓库 README 和各实验说明。
