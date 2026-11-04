# P4：双向 DAB DC/DC 建模与控制

已完成独立低压教学 SPS 模型：9 个稳态工况、39 个有限扫描点、6 项测试和 9 份原始 CSV 的回读积分验证。全部为理想模型离线仿真，未进行硬件测量。

Toshiba RD264 的正式名称为 **Full SiC MOSFET 10kW Isolated Bidirectional DC-DC Converter**，采用双有源桥（DAB）拓扑。[官方入口](https://toshiba.semicon-storage.com/us/semiconductor/design-development/referencedesign/detail.RD264.html)

本次模型是新增的独立实现，参数不来自 RD264，未取得原厂源码，也不声称完整复现。原始来源及许可记录见 [SOURCES.md](SOURCES.md)。

## 运行方法

仅依赖 Python 标准库，已用 Python 3.14.4 实际运行，无须安装额外库。本机 PowerShell 命令：

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p4-dab'
& 'E:\python.exe' -B .\run_experiment.py
```

其他机器可在此目录执行 `python -B run_experiment.py`；单独验证用 `python -B -m unittest -v test_dab_sps`。代码使用 Python 3.10+ 语法/API，其他版本未实测。默认重新生成 `results/` 同名文件；保留已有结果时用 `--output results-rerun` 指定另一个目录。运行失败会保留已生成数据并写入输出目录的 `failure.log`。

## 文件与证据

| 文件 | 内容 |
| --- | --- |
| `dab_sps.py` | 电感时域模型、解析功率与波形采样 |
| `run_experiment.py` | 工况、扫描、CSV 导出与回读、测试日志 |
| `test_dab_sps.py` | 手算、方向、变比、漏感缩放、能量和周期性测试 |
| `MODEL.md` | 变量定义、SPS 关系、积分方法及限制 |
| `results/cases.csv` | 9 个工况的参数、功率、峰值和 RMS 电流 |
| `results/waveforms/*.csv` | 每个工况两个周期的原始分段波形 |
| `results/scan.csv` | 39 点有限扫描完整结果 |
| `results/csv_checks.csv` | 落盘波形的回读积分误差 |
| `results/tests.log` | 实际测试输出及退出码 |
| `results/run_metadata.json` | 时间、解释器版本、脚本参数和求解方法 |
| `results/RESULTS.md` | 自动生成的结果说明 |

CSV 单位为 SI：`t0_s/t1_s` 是区间起止时间；`v1_v/v2_prime_v/vL_v` 为区间内恒定电压；`iL0_a/iL1_a` 为电流两端值，均折算到第一侧；`p1_avg_w/p2_avg_w` 为区间平均功率。包含全部开关边界，每周期约 200 个采样区间；这些只是已求解直线段的细分，不是积分步长。本步未生成绘图文件。

## 本次验证结果

教学假设：V1 = 24 V，V2 默认 12 V，变比 N1/N2 = 2，20 kHz，第一侧总串联等效电感 100 µH。正相移表示第二侧桥滞后，正功率由第一侧流向第二侧。

| 工况 | 时域功率 / W | 第一侧峰值 / A | 第一侧 RMS / A |
| --- | ---: | ---: | ---: |
| 电压匹配，+30° | 20 | 1.000000 | 0.942809 |
| 电压匹配，−30° | −20 | 1.000000 | 0.942809 |
| 电压匹配，0° | 0 | 0 | 0 |
| nV2/V1 = 0.75，+30° | 15 | 1.500000 | 0.924211 |
| nV2/V1 = 1.25，+30° | 25 | 1.750000 | 1.139566 |
| nV2/V1 = 0.75 或 1.25，0° | 0 | 0.750000 | 0.433013 |

全部工况见 [运行结果](results/RESULTS.md)。扫描为 3 个电压比 × 13 个相移（−90° 至 +90°，步进 15°），最大解析/时域功率绝对误差为 2.132e−14 W。6 项测试通过，9 份 CSV 回读积分通过。接近浮点精度的误差来自理想分段线性模型，不代表硬件准确度。

## 下一小步

后续可逐项开展绘图或控制改造。当前未包含启动、方向切换瞬态、闭环保护、损耗、效率或 ZVS 模型；模型边界及推导见 [MODEL.md](MODEL.md)。

第一阶段以离线仿真为目标，不需要物理开发板。本目录不包含上板、写卡或高压硬件运行步骤。
