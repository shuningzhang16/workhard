# 硬件实验

围绕数字电源、FPGA 数据采集和双向 DAB 变换器开展学习、实现与验证。

| 项目 | 目录 | 当前阶段 |
| --- | --- | --- |
| P1：TI C2000 Buck 数字电源 | [experiments/p1-c2000-buck](experiments/p1-c2000-buck/) | 真实 C 控制核心闭环运行 36,006 拍，与 Python 一致；目标编译通过、输出禁用；保留量化清除盲区 |
| P2：ZCU104 FPGA 数据采集 | [experiments/p2-zcu104-daq](experiments/p2-zcu104-daq/) | AXI-Lite、Simple S2MM、有界队列通过；新增进程 CPU 时间及独立 RTL 延迟/FIFO 峰值测量 |
| P4：双向 DAB 建模与控制 | [experiments/p4-dab](experiments/p4-dab/) | 连续换流接入功率 PI/采样保护，55 项测试通过；保留同接收功率损耗比较、未匹配点及过流峰值 |

系统框图与边界见 [系统说明](docs/SYSTEMS.md)，已有数据的可编辑波形图见 [图表与复现](figures/README.md)。

主要数值、测试证据和实际失败定位见 [结果索引](docs/RESULTS.md)。

学习顺序、关键代码路径、练习、面试问答和项目讲解稿见 [学习与讲解指南](docs/LEARNING.md)。

上传后的代码还会运行 [GitHub 离线检查](https://github.com/shuningzhang16/workhard/actions/workflows/offline.yml)。前阶段代码 `b45f667` 的 [三个任务均成功](https://github.com/shuningzhang16/workhard/actions/runs/42053855322)，新增阶段按各自提交核对结果。触发规则、日志位置和验证范围见 [CI 说明](docs/CI.md)。

## 一次复跑离线检查

仓库根目录运行 `python -X utf8 scripts/check_offline.py`，或用 `--only p1`、`--only p2`、`--only p4` 单独检查。本机正常解释器为 `E:\python.exe`。脚本调用各实验已有的 Python 测试、Icarus RTL 仿真及 GCC 主机 C 测试；不会运行硬件或重写已提交的结果。

P1/P4 的模型只需要 Python 标准库；P1 的 C 对照另需 GCC。P2 需要 Icarus Verilog 和 GCC；Windows 下使用 WSL Ubuntu-22.04 的 GCC。本机 Icarus 位于实验 `.tools/`，新机器需要自行具备这些依赖，脚本不自动安装。绘图另需 matplotlib。每次检查的日志和结果保存在带时间的 `.runs/` 目录，未加入 Git；出错时保留输出并继续其他独立检查，最终退出码反映是否有失败。已提交的阶段证据仍在各实验的 `results*`、`simulation/`、`host_c/results/` 和 `evidence/` 目录。

当前统一入口包含七项检查：P1 的 Python、C 回放和真实 C 闭环；P2 的 RTL 功能、FIFO 延迟和包含上游检查的队列入口；P4 的自动发现测试。2026-11-06 本机七项全部通过，含 36,006 拍 C 闭环、独立短接管试验、6 组 RTL 测量和 55 项 DAB 测试。[本轮日志与退出码](verification/2026-11-06-integration/)、[分阶段结果](docs/RESULTS.md)。旧记录只证明对应版本。

通用综合需 Yosys，单独运行 `python scripts/check_synthesis.py` 和 `python scripts/check_synthesis.py --control`。GitHub P2 任务自动执行这两条命令。SPICE 对照、目标器件 Vivado 工程和主机 C 的验证边界在各实验说明中单独记录，当前仍没有完成板端测量。

可运行环境仍有缺口：完整 Vivado/Vitis/BSP 尚未取得构建结果；[Simulink 构建脚本](docs/SIMULINK.md) 未在 MATLAB 中运行；LTspice 本机启动超时，准备的网表未取得结果。这些与上板验证分别记录，不能合称为“只差上板”。详见 [工具状态](verification/tooling/README.md)。

## 版本与来源

- 先提交可获取、允许再分发的原始参考源码，再逐项提交实现和改进，使用 Git 历史查看变化。
- 厂商源码保留原有版权和许可证；各项目说明原始来源、版本、适配情况与后续新增内容。
- 未取得的原厂源码不以自建模型替代冒充。自建模型明确记录参数假设。
- 仿真、离线验证和实物测量分别标注。当前没有完成硬件实测。
- 本仓库仅包含三个实验相关内容。

## 实验范围

P1 先做 Buck 与控制算法的离线仿真；P2 先用内部数据源验证 RTL 和数据格式；P4 以 SPS 双向功率建模和仿真为主。后续硬件验证单独安排。
