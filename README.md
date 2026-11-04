# 硬件实验

围绕数字电源、FPGA 数据采集和双向 DAB 变换器开展学习、实现与验证。

| 项目 | 目录 | 当前阶段 |
| --- | --- | --- |
| P1：TI C2000 Buck 数字电源 | [experiments/p1-c2000-buck](experiments/p1-c2000-buck/) | PWM 保护及恢复通过；独立 C 控制模块与 Python 完成 26,004 点对照；保留 ngspice 独立验证 |
| P2：ZCU104 FPGA 数据采集 | [experiments/p2-zcu104-daq](experiments/p2-zcu104-daq/) | AXI-Lite 启停/计数、Simple S2MM 主机流程通过；RTL 与通用综合网表重放一致 |
| P4：双向 DAB 建模与控制 | [experiments/p4-dab](experiments/p4-dab/) | 功率 PI、正反向跟踪、饱和返回及五个固定参数点通过；保留 SPS/EPS/换流分析 |

系统框图与边界见 [系统说明](docs/SYSTEMS.md)，已有数据的可编辑波形图见 [图表与复现](figures/README.md)。

主要数值、测试证据和实际失败定位见 [结果索引](docs/RESULTS.md)。

上传后的代码还会运行 [GitHub 离线检查](https://github.com/shuningzhang16/workhard/actions/workflows/offline.yml)。首次三个实验任务均已通过，触发规则、日志位置和验证范围见 [CI 说明](docs/CI.md)。

## 一次复跑离线检查

仓库根目录运行 `python -X utf8 scripts/check_offline.py`，或用 `--only p1`、`--only p2`、`--only p4` 单独检查。本机正常解释器为 `E:\python.exe`。脚本调用各实验已有的 Python 测试、Icarus RTL 仿真及 GCC 主机 C 测试；不会运行硬件或重写已提交的结果。

P1/P4 的模型只需要 Python 标准库；P1 的 C 对照另需 GCC。P2 需要 Icarus Verilog 和 GCC；Windows 下使用 WSL Ubuntu-22.04 的 GCC。本机 Icarus 位于实验 `.tools/`，新机器需要自行具备这些依赖，脚本不自动安装。绘图另需 matplotlib。每次检查的日志和结果保存在带时间的 `.runs/` 目录，未加入 Git；出错时保留输出并继续其他独立检查，最终退出码反映是否有失败。已提交的阶段证据仍在各实验的 `results*`、`simulation/`、`host_c/results/` 和 `evidence/` 目录。

最新统一运行的六项任务全部通过：Buck 10 项与 C 控制逻辑 26,004 点对照；RTL source/FIFO 六组及 AXI-Lite 接口；帧校验 16 项与 Simple S2MM 13 项；DAB 33 项。[完整日志与退出码](verification/2026-11-04-control/)。前一轮日志仍保留在 [早期验证记录](verification/2026-11-04/)。

通用综合需 Yosys，单独运行 `python scripts/check_synthesis.py` 和 `python scripts/check_synthesis.py --control`。GitHub P2 任务自动执行这两条命令。SPICE 对照、目标器件 Vivado 工程和主机 C 的验证边界在各实验说明中单独记录，当前仍没有完成板端测量。

## 版本与来源

- 先提交可获取、允许再分发的原始参考源码，再逐项提交实现和改进，使用 Git 历史查看变化。
- 厂商源码保留原有版权和许可证；各项目说明原始来源、版本、适配情况与后续新增内容。
- 未取得的原厂源码不以自建模型替代冒充。自建模型明确记录参数假设。
- 仿真、离线验证和实物测量分别标注。当前没有完成硬件实测。
- 本仓库仅包含三个实验相关内容。

## 实验范围

P1 先做 Buck 与控制算法的离线仿真；P2 先用内部数据源验证 RTL 和数据格式；P4 以 SPS 双向功率建模和仿真为主。后续硬件验证单独安排。
