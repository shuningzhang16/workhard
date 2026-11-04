# 硬件实验

围绕数字电源、FPGA 数据采集和双向 DAB 变换器开展学习、实现与验证。

| 项目 | 目录 | 当前阶段 |
| --- | --- | --- |
| P1：TI C2000 Buck 数字电源 | [experiments/p1-c2000-buck](experiments/p1-c2000-buck/) | PI/保护/PWM 模型通过，ngspice 已实际运行并完成独立对照 |
| P2：ZCU104 FPGA 数据采集 | [experiments/p2-zcu104-daq](experiments/p2-zcu104-daq/) | 顶层 RTL→C 联测通过；提供待完整 Vivado 验证的 Tcl 工程入口 |
| P4：双向 DAB 建模与控制 | [experiments/p4-dab](experiments/p4-dab/) | SPS/EPS 比较、连续电流换向、采样保护和换流极性分析通过 |

系统框图与边界见 [系统说明](docs/SYSTEMS.md)，已有数据的可编辑波形图见 [图表与复现](figures/README.md)。

主要数值、测试证据和实际失败定位见 [结果索引](docs/RESULTS.md)。

上传后的代码还会运行 [GitHub 离线检查](https://github.com/shuningzhang16/workhard/actions/workflows/offline.yml)。首次三个实验任务均已通过，触发规则、日志位置和验证范围见 [CI 说明](docs/CI.md)。

## 一次复跑离线检查

仓库根目录运行 `python -X utf8 scripts/check_offline.py`，或用 `--only p1`、`--only p2`、`--only p4` 单独检查。本机正常解释器为 `E:\python.exe`。脚本调用各实验已有的 Python 测试、Icarus RTL 仿真及 GCC 主机 C 测试；不会运行硬件或重写已提交的结果。

P1/P4 只需要 Python 标准库。P2 需要 Icarus Verilog 和 GCC；Windows 下使用 WSL Ubuntu-22.04 的 GCC。本机 Icarus 位于实验 `.tools/`，新机器需要自行具备这些依赖，脚本不自动安装。绘图另需 matplotlib。每次检查的日志和结果保存在带时间的 `.runs/` 目录，未加入 Git；出错时保留输出并继续其他独立检查，最终退出码反映是否有失败。已提交的阶段证据仍在各实验的 `results*`、`simulation/` 和 `evidence/` 目录。

本轮统一运行已通过：Buck 8 项、RTL 六组、主机 C 16 项、DAB 25 项。日志副本见 [2026-11-04 验证记录](verification/2026-11-04/)。SPICE 对照与 Vivado 入口的验证范围在各实验说明中单独记录。

## 版本与来源

- 先提交可获取、允许再分发的原始参考源码，再逐项提交实现和改进，使用 Git 历史查看变化。
- 厂商源码保留原有版权和许可证；各项目说明原始来源、版本、适配情况与后续新增内容。
- 未取得的原厂源码不以自建模型替代冒充。自建模型明确记录参数假设。
- 仿真、离线验证和实物测量分别标注。当前没有完成硬件实测。
- 本仓库仅包含三个实验相关内容。

## 实验范围

P1 先做 Buck 与控制算法的离线仿真；P2 先用内部数据源验证 RTL 和数据格式；P4 以 SPS 双向功率建模和仿真为主。后续硬件验证单独安排。
