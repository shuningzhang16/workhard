# P4：双向 DAB DC/DC 建模与控制

已完成独立低压教学 SPS 模型：9 个稳态工况、39 个有限扫描点、6 项测试和 9 份原始 CSV 的回读积分验证。全部为理想模型离线仿真，未进行硬件测量。

第二步已完成第一侧桥 EPS 的同功率比较：12 个轻载/中载正反向工况、2 个无解工况、182 个候选记录；原 SPS 与新增 EPS 共 12 项测试通过。定义与结果见 [EPS.md](EPS.md)。

第三步已完成保留电感状态的 SPS RL 瞬态、方向切换、采样过流/母线输入越限锁存及显式恢复。4 个工况、19 项测试和原始 CSV 回读通过；首次快速恢复再次锁存的失败证据和回归测试均已保留。详见 [TRANSIENT.md](TRANSIENT.md)。

第四步已完成已有 SPS/EPS 波形的逐开关沿电流极性分析：40 个周期波形、320 个桥臂事件、25 项测试通过。这是软开关的必要极性筛查，未确认实际 ZVS。电流方向、边界及来源见 [COMMUTATION.md](COMMUTATION.md)。

第五步已完成固定母线下的离散传输功率 PI 环，仅使用上一已完成周期的实算功率；3 个工况、30 项测试通过，包含正向阶跃、反向指令、不可达指令的抗积分饱和及保护恢复。详见 [POWER_LOOP.md](POWER_LOOP.md)。

第六步固定上述 PI 增益，在指定的 5 个 V2/R 参数点运行同一 5→15→−10→0 W 序列。20 段均在各自 10 ms 窗口内进入并保持误差带，无保护事件；33 项测试和 5 份完整波形回读通过。仅代表这五点，详见 [POWER_POINTS.md](POWER_POINTS.md)。

第七步加入局部死区换流：共享电感、8 个线性电荷等效电容及二极管钳位，以开通前节点电压判定。24 组、192 个待开通器件、38 项测试及 6 个实际 ngspice 独立电路对照通过，保留无法完成的换流。器件假设、初学者解释和局限见 [DEADTIME.md](DEADTIME.md)。

第八步已串联连续整周期 RLC 换流与解析非死区 RL，开通瞬间保持电感电流，并单独记录母线电荷和双电容重分配能量。一次真实的越轨回返事件漏检已留证、隔离修复并补上下轨回归；16 个固定角度工况各运行 100 周期，44 项测试与全程波形回读通过。实际功率误差完整保留，该阶段尚未重新匹配功率。详见 [CONTINUOUS.md](CONTINUOUS.md)。

第九步按实际接收端匹配功率：正向 P2、反向 −P1；10 次尝试中 9 个匹配，1 个指定区间未匹配，47 项测试及 9 份完整波形回读通过。新增逐管沟道及栅驱的部分损耗后处理，保留 13.5 W 时 EPS 的 RMS 略低但损耗更高的反例；未将后处理反馈到物理波形，也不宣称完整效率。详见 [LOSS_BUDGET.md](LOSS_BUDGET.md)。

第十步已将原功率 PI、采样保护和显式恢复接入持续保存四节点/Coss 状态的物理模型。采用固定主载波时钟，支持过零换向、重叠死区及同刻保护优先；16 个固定角回归、55 项测试和 6 份完整波形检查通过。20 W→−15 W 在 4.15 ms 入带，饱和返回 10 W 在 3.70 ms 入带；过流峰值约 1.655 A 如实保留。详见 [CONTINUOUS_CONTROL.md](CONTINUOUS_CONTROL.md)。

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

EPS 比较可执行 `E:\python.exe -B run_eps_comparison.py`，数据保存在独立的 `results_eps/`。电压比 0.75、±2.7 W 时 RMS 电流降低 31.183%；电压比 1 和 1.25 的所查目标未找到改善，选回 SPS。最大目标匹配误差 2.134e−11 W，全部 24 份波形 CSV 回读通过。详见 [比较结果](results_eps/RESULTS.md)。

第三步执行 `E:\python.exe -B -X utf8 run_transient_demo.py`，数据在 `results_transient/`。模型使用教学假设 R=0.5 Ω，未每周期扣除电流均值；正反向尾段 P2 分别为 19.748482 W、−20.192294 W，4 个工况最大全程能量残差约 1.127e−16 J。保护检测有采样延迟，不是硬件安全保证。

第四步执行 `E:\python.exe -B -X utf8 run_commutation_analysis.py`，结果在 `results_polarity/`。m=0.75、±2.7 W 时，SPS 有 4 个沿方向相反，所选 EPS 的 8 个沿均满足必要极性；m=1.25 的轻载点仍有 4 个沿方向相反。8 个沿全部满足也不能确认 ZVS，缺失 Coss/Qoss、死区及寄生模型。

第五步执行 `E:\python.exe -B -X utf8 run_power_loop.py`，输出在 `results_power_loop/`。20 W→−15 W 在 4.150 ms 内进入并保持本次误差带；100 W 请求受限到约 31.172552 W，降回 10 W 后 3.750 ms 恢复，尾段误差 0.008278 W。该 PI 环的增益和误差带均为明确教学设定，原保护和物理检查不变。

第六步执行 `E:\python.exe -B -X utf8 run_power_points.py`，独立输出在 `results_power_points/`。V2=9/12/15 V、R=0.5 Ω，以及 V2=12 V、R=0.25/1 Ω 五点中，最慢入带 5.000 ms，最大尾段平均误差绝对值 0.006607 W；未改 PI 增益或保护阈值。完整参数和逐段结果均保存为 CSV。

第七步执行 `E:\python.exe -B -X utf8 run_deadtime.py` 和 `E:\python.exe -B -X utf8 verify_deadtime_spice.py`，前者输出在 `results_deadtime/`；SPICE 复跑自动使用 `.runs/deadtime-spice-时间戳/` 新目录，历史成功证据仍在 `results_deadtime_spice/`。2.7 W 正向 EPS 的有利极性在 150 ns 时只完成 4/8 个沿，500 ns 时完成 8/8；反向 EPS 在 500 ns 时仍只有 6/8。ngspice 最大节点差约 1.19 mV；同功率仅指提供初态的理想周期解，不是含死区的完整稳态或效率结果。

第八步执行 `E:\python.exe -B -X utf8 run_continuous.py`，输出在 `results_continuous/`。+2.7 W 原理想角度、500 ns 死区下，连续模型的 SPS/EPS 实际 P2 分别为 4.854947/2.146260 W；两者已不等功率。所有电流跨窗口保留，每周期约 12–22 条区间/开通记录，无整周期统一微步长；R、二极管、开通电荷能量只计一次。

本步先单独提交和上传。当前仍未包含输出电压/电池动态、硬件控制实现、器件损耗/效率或完整 ZVS 模型；各步的假设与证据分别保留在对应说明中。

第一阶段以离线仿真为目标，不需要物理开发板。本目录不包含上板、写卡或高压硬件运行步骤。
