# ngspice 独立瞬态对照：已实际执行

本步在 **WSL Ubuntu-22.04（22.04.5 LTS、x86_64）** 中实际运行了 **ngspice 36**，使用此前提交的固定占空比理想 Buck 网表。结论仅覆盖这个理想脉冲源、L、C、R 网表；本阶段当时没有运行 LTspice，也没有器件损耗、效率或硬件测量结论。2026-11-06 后续已实际运行 LTspice，见[单独的新证据](ltspice_results_20261106/README.md)。

## 工具取得与执行范围

WSL 初始没有 ngspice。通过现有 Ubuntu 包索引，从官方 `jammy-updates/universe` 下载 `ngspice=36+ds-1ubuntu0.1`，deb 文件 **2,352,208 字节**，解压至本实验 `.tools/ngspice/`。所需动态库在 WSL 已存在，没有安装额外依赖，没有 `apt install`、系统 PATH 或系统配置修改。

`.tools/` 已在本实验 `.gitignore` 中排除。包内的第三方版权文件保留在解压目录，实际程序版本输出也原样保存。官方下载信息见 [Ubuntu ngspice 包](https://packages.ubuntu.com/jammy-updates/ngspice)，本次下载与动态依赖检查记录为 `evidence/ngspice-tool-setup.txt`。

先原样执行了上一阶段上传的网表，保留 `spice_results/original_netlist.cir` 与 `original_netlist.log`。它的标题仍有当时的“NOT RUN”历史注释，日志随后记录了实际成功分析与测量。当前 `ideal_buck_fixed.cir` 仅更新了运行状态注释，没有改变电路参数。

随后生成两个输出探针网表：复制相同电路，只调整瞬态保存范围和导出指令，分别保存稳态窗口、从零启动窗口。实际使用：

```text
wsl.exe -d Ubuntu-22.04 -- .tools/ngspice/usr/bin/ngspice -n -b simulation/spice_results/steady.cir
wsl.exe -d Ubuntu-22.04 -- .tools/ngspice/usr/bin/ngspice -n -b simulation/spice_results/startup.cir
```

两个进程均正常返回。日志中的 `can't find init file` 是本地解压运行时的初始化文件提示；此 RLC 网表不依赖初始化脚本或额外器件模型库。脉冲源未另写 DC 参数，因此还有采用其 t=0 瞬态值的提示。提示均原样保留，没有通过修改电路或隐藏日志来消除；没有将这个简单网表的运行成功推广为全部 ngspice 模型库已可用。

## 初始条件对齐

网表明确使用：

```spice
L1 sw out 220u IC=0
C1 out 0 470u IC=0
.tran 0.25u 60m 59.6m 0.25u uic
```

这与 Python 的 `iL(0)=0 A, vO(0)=0 V` 对齐。`uic` 指定使用给定初始条件，避免默认 DC 工作点初始化；`tstart=59.6m` 只限制保存起点，实际瞬态仍从 t=0 积分到 60 ms。两条含义依据 [ngspice 官方用户手册](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf) 的 `.TRAN` 与 `.IC` 说明，并通过本次输出日志和启动探针核对。

为了直接保留启动证据，另运行相同元件和初始条件的：

```spice
.tran 0.05u 200u 0 0.05u uic
```

两个日志都明确记录使用瞬态初始条件。启动探针首个保存点为 **t=10 ps**，输出 **8.70406e-17 V**，电感电流 **4.09091e-9 A**，与零状态开始、随后脉冲上升相符。首点开关节点为 0.09 V，源于 1 ns 上升沿已经进行 10 ps，不能把它误解为预充电的电容初始电压。

SPICE 脉冲使用 1 ns 上升/下降沿，平顶宽度为 `D×T−1 ns`，使完整脉冲面积仍为 `Vin×D×T`。Python 使用瞬时理想边沿。因此 L/C/R、Vin、D、频率和初始状态相同，边沿形状不完全相同；本步不声称两个连续时间激励逐点完全一致。

## 稳态窗口对照

条件：Vin=9 V、D=2/9、fs=50 kHz、L=220 µH、C=470 µF、R=4 Ω。Python 参考来自第四步实际运行、最大子步 0.25 µs 的原始波形。

两边都取约 **59.6–60.0 ms** 的有限窗口。ngspice 第一个实际保存点为 59.6000001 ms，比 Python 窗口起点晚 0.1 ns，结束点相同到浮点精度。脚本按每份原始波形的实际首尾时间计算加权均值，没有补造 t=59.6 ms 的 SPICE 数据；精确端点写在 `summary.json`。这个很小的窗口差也包含在下面的数值差中。

峰峰值统一采用**整个窗口最大值减最小值**；不同于第四步报告的“20 个周期峰峰值的平均”。均值按原始不等间隔时间点做梯形积分，不使用点数平均。

| 指标 | Python 原始波形 | ngspice 原始波形 | SPICE−Python |
|---|---:|---:|---:|
| 输出时间均值 | 2.000000230419 V | 2.000000230454 V | +3.52e-11 V |
| 电感电流时间均值 | 0.500000075717 A | 0.500000093380 A | +1.76629e-8 A |
| 输出窗口峰峰纹波 | 0.752197878 mV | 0.751887738 mV | -0.310140 µV（-0.041231%） |
| 电感窗口峰峰纹波 | 0.141422437 A | 0.141414888 A | -7.54810 µA（-0.005337%） |

相对差以 Python 数值为分母，不是相对真实硬件的测量误差。差异可以受有限边沿、积分和极值取样网格及窗口端点影响，本步没有分离各项误差贡献。接近的结果支持两个独立实现对当前理想稳态案例的一致性，不表示具备表中小数位对应的硬件精度。

原网表自身 `.meas` 输出也得到约 2 V、0.5 A、0.7518877 mV 和 0.1414149 A，见原始日志。后续导出使用 17 位文本精度，并在 Python 标准库中复算波形均值和峰峰值。

## 检查与证据

本轮独立对照脚本的 **8 项检查通过**：

- ngspice 输出均值相对 2 V 的绝对差 <1e-5 V，电感均值相对 0.5 A 的绝对差 <1e-5 A。
- 输出、电感纹波相对原基本解析式均在 2% 内。这些直流和纹波判据与已提交开关模型的检查一致，没有放宽。
- 首个启动保存点不晚于 1 ns，且输出与电感电流均接近零。
- 导出的 SPICE 数据全部有限。

此前平均模型、保护和开关模型的实现及测试条件保持不变。本轮没有运行失败，未增加大范围参数扫描。

| 文件 | 内容 |
|---|---|
| `spice_results/original_netlist.cir`、`original_netlist.log` | 上一步提交网表的原样执行证据 |
| `spice_results/ngspice-version.txt` | 实际程序版本与原版权输出 |
| `spice_results/steady.cir`、`steady.log` | 稳态探针网表与原始程序输出 |
| `spice_results/steady.dat`、`steady.csv` | 约 59.6–60 ms 的 2,200 个原始保存点；CSV 仅统一列名和格式 |
| `spice_results/startup.cir`、`startup.log` | 零状态启动探针与原始程序输出 |
| `spice_results/startup.dat`、`startup.csv` | 10 ps–200 µs 的 4,272 个保存点 |
| `spice_results/comparison.csv`、`summary.json` | 数值对照、实际窗口、初始点、命令和检查结果 |
| `evidence/spice-comparison-run.txt` | 实际对照脚本输出 |

## 复现

在实验目录执行。首次需要本地 ngspice 包时，运行只下载和解压的脚本；本机已经完成这一步。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
wsl.exe -d Ubuntu-22.04 -- sh simulation/setup_ngspice.sh
& 'E:\python.exe' .\simulation\run_spice_comparison.py
```

如果要重新生成 Python 参考波形，先运行 `simulation/run_switching.py`；对照脚本读取其 `switching_results/fixed_duty_0p25us_waveform.csv`。源码和有限窗口数据可上传；`.tools/` 中的 deb 与解压工具留在本地，不修改系统工具环境。

本步仅完成理想固定占空比的 SPICE 交叉验证；未验证 SPICE 闭环 PI、保护联动、LTspice、真实开关器件或硬件。
