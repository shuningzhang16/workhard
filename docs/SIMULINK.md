# DAB 的 Simulink 模型生成入口

**当前状态：已提供构建和运行脚本，尚未在 MATLAB/Simulink 中执行。** 本机没有可用的 MATLAB/Simulink 运行时，因此仓库没有伪造 `.slx`、运行日志、波形或通过结果。现有 Python/ngspice 的成功记录不能替代这里的模型编译与运行。

入口为 [`scripts/matlab/build_dab_sps.m`](../scripts/matlab/build_dab_sps.m)。它用标准 Simulink 模块构建一次侧折算的双桥电压源与 R-L 电流模型，不需要 Simscape，不与硬件通信。所用 API 和块参数已对照下方 MathWorks 文档；实际版本兼容性仍需目标环境运行确认。

已做的静态核对包括 8 个块名称与 10 条连接引用一致、文档中的本地文件链接存在。未运行 MATLAB `checkcode`、模型更新/编译或 `sim`，静态核对不能替代这些检查。

## 运行和产物

在安装了 MATLAB 和 Simulink 的电脑中，将 MATLAB 当前目录设为仓库根目录：

```matlab
addpath(fullfile(pwd, 'scripts', 'matlab'));
outputDir = build_dab_sps();       % 构建并运行正、反向，共四次短仿真
open_system(fullfile(outputDir, 'dab_sps_teaching.slx'));
```

若只需要构建模型，使用 `build_dab_sps(false)`。默认 `.slx` 内保存正向 +30° 的输入，打开后可独立运行。脚本不会关闭已有同名模型；先自行保存该模型再重建。

每次调用在仓库忽略目录 `.runs/` 内新建一个独立目录，保留 `matlab.log`、`parameters.mat` 和 `.slx`。运行模式还会保存每个工况的原始 `SimulationOutput` MAT 文件、全程 CSV 及 `metrics.csv`。失败时日志和已产生数据保留；只有四次仿真及数值检查实际结束后，才打印成功信息。

## 模型与参数

两侧桥电压通过 `From Workspace` 输入，`Sum → 1/L → Integrator` 求解：

`L diL/dt = v1 − v2_referred − R iL`。

`SeriesR` 反馈电阻压降，积分器初值为 0 A。电流从开始到结束连续保留，不逐周期居中或重置。Mux/To Workspace 记录 `v1`、`v2_referred` 和 `iL`，脚本由这些实际输出计算端口功率、电阻功耗及能量收支。

| 参数 | 值与含义 |
| --- | --- |
| V1 / V2 | 24 V / 12 V，理想固定母线 |
| n = N1/N2 | 2；第二侧桥电压折算为 nV2，电流 iL 属于第一侧 |
| L / R | 100 µH / 0.5 Ω，第一侧等效串联值 |
| fs | 20 kHz，周期 50 µs |
| 相移 | +30°、−30° 分别独立从 0 A 启动；正相移表示第二桥滞后 |
| 时长 | 每场景 120 周期，即 6 ms；末 10 周期单独统计 |
| 边沿 | 83.333… ns 线性上升/下降沿，属于数值模型假设 |
| 求解器 | 固定步长 ode4；步长为 83.333… ns 和其一半 |

以上全部是本仓库教学参数，不是 RD264 原厂器件或额定工况。模型没有 ADC、PWM 固件、保护动作、闭环 PI、死区/Coss、二极管、磁化或母线电容动态；现有更复杂模型的能力不会自动转移到这份 Simulink 入口。

## 边沿与求解时刻

两个电压源使用同一个 600 点/周期边沿网格；±30° 对应整数 ±50 个网格，因此没有相移取整误差。`From Workspace` 连续采样并线性插值，电压变化发生在理想开关时刻之前的一个网格区间，两个桥都采用相同定义。首次输入在 t=0 使用对应相位的电压，不额外制造一个启动电压斜坡。

基础与细化运行使用完全相同的输入时间点和 83.333… ns 边沿宽度，只把积分步长减半。所有线性段端点都落在求解网格上，因此不依赖 fixed-step 下并不支持的 From Workspace 零交叉定位。若修改相移或边沿参数，必须重新保证网格对齐，不能仅减少 MaxStep 就假定跳变已精确定位。[From Workspace 参数与插值规则](https://www.mathworks.com/help/simulink/slref/fromworkspace.html)、[求解器配置](https://www.mathworks.com/help/simulink/gui/solver.html)

## 准备的检查，以及尚未取得的结果

脚本在运行时会检查输出有限性、时间范围、未抽样的固定步长记录、初始电流、两桥输入值，以及相移与末窗口功率方向。它还使用独立的分段线性输入 R-L 解析更新计算参考电流；解析更新不会读取 Simulink 的电流状态。

预设数值容差为：最大参考电流差 <10 µA、累计能量残差 <1 µJ；步长减半后末窗口平均 P2 差 <0.01 W、RMS 电流差 <0.1 mA。容差和输入先写入代码，尚无实际通过结论。失败时应检查已保存输出、求解时刻与模型连接，不能直接放宽容差。

能量残差定义为 `∫(p1−p2−R iL²)dt − Δ(½L iL²)`，由输出波形梯形积分计算。它检查这份 R-L 模型的收支，不是实际变换器效率。串联损耗存在时，固定相移下 P2 不应被硬套为无损模型的精确 ±20 W。

与 [`dab_sps.py`](../experiments/p4-dab/dab_sps.py) 的无损、零直流偏置周期解相比，这里有 R、有限边沿、0 A 启动和真实暂态。与 [`dab_transient.py`](../experiments/p4-dab/dab_transient.py) 相比，这里使用固定 ±30°，没有相移斜率限制或保护状态机，因此不能直接逐行比较其启动结果。

## 官方接口依据

- 用 [`add_block`](https://www.mathworks.com/help/simulink/slref/add_block.html) 和 [`save_system`](https://www.mathworks.com/help/simulink/slref/save_system.html) 生成标准块模型并保存 SLX。
- 输入默认值通过 [`Simulink.ModelWorkspace.assignin`](https://www.mathworks.com/help/simulink/slref/simulink.modelworkspace.assignin.html) 写入模型工作区；各次仿真用 [`SimulationInput.setVariable`](https://www.mathworks.com/help/simulink/slref/simulink.simulationinput.setvariable.html) 覆盖指定模型工作区变量。
- 输出使用 [`To Workspace`](https://www.mathworks.com/help/simulink/slref/toworkspace.html) 的 Timeseries 格式，并从本次 `SimulationOutput` 取得，避免读取上一次留在工作区的同名结果。

下一项真实验证是：在具备许可证的 MATLAB/Simulink 环境执行上述入口，查看模型连线和四份输出，并保存版本、日志和实际结果；目前这一项仍未完成。
