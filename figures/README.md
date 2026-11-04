# 实验图表

图表直接读取仓库内已经执行得到的 CSV，使用 Python/matplotlib，不生成或替换实验数据。默认导出可编辑 SVG/PDF 和 PNG 预览。全部数值为仿真，不是硬件测量。

## 图的目的与数据

| 图 | 要回答的问题 | 数据与范围 |
| --- | --- | --- |
| `p1_pi_response` | 当前 PI 能否在软启动与两种扰动后回到目标电压？ | P1 `simulation/results/` 三个工况的全部 5,001 个采样点，各一个面板；统一时间和电压刻度 |
| `p4_sps_transfer` | SPS 如何改变功率方向，电压不匹配时是否仍有交流电流？ | P4 `results/scan.csv` 全部 39 点；左图功率、右图 RMS 电流，按三个电压比分组 |

这是确定性仿真曲线，不是重复试验的均值，不绘制统计误差条或置信区间。没有过滤缺失值、截取有利区间、平滑或重采样。输入 CSV 保持原样；图中单位转换仅为秒→毫秒。

## 复现

在仓库根目录执行 `python figures/plot_results.py`，需要 matplotlib。输出位于 `figures/output/`。本机使用已有 Anaconda Python 3.13.5 和 matplotlib，不改变实验模型使用的解释器。

图的排版以实验报告为目标，宽 183 mm、白底、至少 8 pt 正文字。图源、原始 CSV、可编辑导出和预览共同保留。可选的版面审查脚本存在于 Python 搜索路径时，绘图脚本会额外保存面板对齐检查结果；普通复现不依赖它。

## 预览

![Buck PI 仿真响应](output/p1_pi_response.png)

![DAB SPS 功率与电流](output/p4_sps_transfer.png)

图表检查记录见 [QA.md](QA.md)。
