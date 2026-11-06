# P4 原生 PLECS 工程准备与真实平台状态

**状态（2026-11-06）：官方 PLECS 5.0.7 Demo 中的签名 DAB 原例已实际运行至 0.8 s，取得完成窗口和全程波形截图。** 输出约 380 V，0.4 s 负载阶跃前后电流约 2.63 A→5.26 A、功率约 1 kW→2 kW，电压暂降后恢复。这些是可见波形的近似读数，没有导出原始数组或计算精确误差；见[全程波形](evidence/03_official_dab_secondary_completed.png)与[完成后的电路](evidence/04_official_dab_completed_schematic.png)。原例副边是电容与电阻负载，不能证明持续反向传能。固定双电源正反向对照尚未完成。

Demo 只允许新建模型或打开官方签名示例；自建 `dab_sps_forward` 文件仍因 `Invalid signature` 无法加载。下方 24 V／12 V 数值是独立解析期望值，不是本次 95 V／380 V 官方原例的输出。

## 文件

- `build_models.py`：独立编写的原生 PLECS 输入生成器，无 RPC、仿真结果读取或导出功能。
- `models/dab_sps_forward.plecs`：+30° 正向 SPS 原生输入。
- `models/dab_sps_reverse.plecs`：−30° 反向 SPS 原生输入。
- `reference_rl.py`：仅用 Python 标准库计算分段恒压 R-L 解析参考；不读 PLECS 进程或数据。

这些 `.plecs` 文件是新编写的模型源文件，不是从 Demo 保存或导出的文件。**它们需要合法完整/试用许可才能从文件加载；5.0.7 Demo 不能直接打开这些未签名输入。** 实际格式兼容性、连接和运行仍需具备相应许可的 PLECS 检查。端口编号已按官方 5.0.7 包内组件及示例源码核对，包括 SignalMux 的输出端口 1、输入端口 2/3；这不替代原生解析和仿真。

从仓库根目录生成另一份输入时，使用一个不存在的新目录：

```powershell
python -B experiments/p4-dab/plecs/build_models.py .runs/plecs_inputs_next
python -B experiments/p4-dab/plecs/reference_rl.py
```

生成器拒绝复用已有输出目录，不清理任何文件。当前源码和已附输入按内容核对一致。

## 电路和范围

两个 24 V／12 V 固定直流母线、八个理想 `MosfetWithDiode` 开关、2:1 理想变压器、一次侧 100 µH 电感及 0.5 Ω 串联电阻。四个互补 Pulse Generator 以 20 kHz 驱动两座全桥；副桥相移为 ±30°，正值表示滞后。一次侧电流由零开始，仿真时长 6 ms（120 周期）。

模型包含实际电气开关网络，不是由 Python 波形驱动的回放。母线、变压器和开关都是理想教学模型：无死区、Coss、磁化、非零二极管压降、器件热模型、母线动态、PI 或采样保护。它首先核对平台上的基础 SPS R-L 电路，不能替代仓库连续死区与保护模型的验证，也不等同 RD264 原厂工程。

`v1` 测主桥差分电压，`v2` 测副桥差分电压，`iL` 测流入变压器一次侧的电流。示波器显示 `v1`、`2*v2`、`iL`。可见 Display 显示逐周期平均 P1、P2、RMS 电流及电阻功耗：

- P1 = mean(v1 * iL)，正值为第一侧输入。
- P2 = mean(2 * v2 * iL)，正值为第二侧输出。
- R_loss = 0.5 * mean(iL²)。反向时 P1/P2 都为负，接收功率是 −P1。

求解设置为 `dopri`、最大步长 0.5 µs、RelTol 1e−8、AbsTol 1e−9；开关边沿由 Pulse Generator 的离散事件指定。实际运行后仍需核对边沿、正负号、终止时间和数值误差。

## 独立解析期望值，尚无 PLECS 对照结果

`reference_rl.py` 对每个开关区间使用 `di/dt = (v1 − n*v2 − R*i)/L` 的指数解析解，并解析积分电荷及 i²；从 0 A 连续推进 120 周期，统计最后一周期。

| 相移 | P1 / W | P2 / W | R_loss / W | Irms / A | Ipeak / A |
| --- | ---: | ---: | ---: | ---: | ---: |
| +30° | 20.19229360 | 19.74848233 | 0.44381127 | 0.94213722 | 1.05142834 |
| −30° | −19.74848233 | −20.19229360 | 0.44381127 | 0.94213722 | 1.05142834 |

表内值只用于后续对照。没有 PLECS 数值误差、通过结论或全量数据导出证据。与 MATLAB 脚本的有限边沿模型相比，这里是理想开关边沿，不能要求所有启动波形逐点相同。

## 已准备的本机环境和剩余操作

官方 Linux 5.0.7 包实际下载长度为 370155935 字节，已在新目录解压；Ubuntu 22.04 的 WSLg 可用，动态库检查没有缺失项。工作目录为：

```text
E:\UserData\Documents\ChatGPT\硬件\.runs\plecs_5_0_7_demo_20261106_01
```

该目录保留官方压缩包、官方示例、解压程序、第一版草稿以及修正端口编号后的第二版输入。它是本机运行准备目录，不应把整套第三方程序或示例上传为本项目源码。没有删除或清理这些文件。

第一次应用读取曾超时；用户恢复界面授权后，已实际完成 Demo 选择，并观察到以下原生限制：只能新建模型或打开官方签名示例；不能保存模型；导出操作禁用；不能使用 PLECS Spice 块。随后原生 Diagnostics 明确拒绝自建输入的签名。

已保留的可见证据（仅窗口截图，不是仿真数据导出）：

- `evidence/01_demo_restrictions.png`：PLECS Demo Mode 的实际限制。
- `evidence/02_native_input_rejected.png`：自建模型被原生签名检查拒绝。

**网页“可建模运行但禁保存”的简略说明不足以推断 Demo 能打开任意自建文件。此前这一推断现已更正。** 不修改签名，不使用脚本、内存、剪贴板或其他方式绕过加载/保存限制。

官方包内已定位的签名示例为 Plexim 的 `dual_active_bridge_converter`（源文件格式版本 4.9，由 5.0.7 发行包提供）：

```text
/mnt/e/UserData/Documents/ChatGPT/硬件/.runs/plecs_5_0_7_demo_20261106_01/extracted/plecs/demos/dual_active_bridge_converter/dual_active_bridge_converter.plecs
```

这是厂商原例，原参数为 95 V 输入、380 V 输出、250 kHz、1 kW 到 2 kW 负载阶跃，含磁性及热模型，不是本项目 24 V／12 V 电路。本轮已从正常文件选择器加载、通过菜单运行，并观察到仿真完成、时间轴达到 0.80 s。以上截图是本机实际结果；厂商程序和示例保留在本地，未作为自编源码上传。保留 Plexim 署名及原始文件。

执行状态及后续步骤：

1. 已完成：从正常 `Open File` 对话框打开官方签名 DAB，核对原厂参数。
2. 已完成：合法运行官方示例到 0.8 s，保留真实终止状态与可见波形。尚未改动原例参数；不能把原厂电压/功率直接当作低压实验结果。
3. 如需与本仓库固定 SPS R-L 模型严格对照，可以在 Demo 界面内合法新建等效模型；从磁性/热闭环原例直接改成固定双母线、开环 ±30°并非只修改两个电压数值。
4. 需要加载已备好的自建源文件或保存完整波形时，提供合法 PLECS Standalone 完整/试用许可，再使用官方功能。自建正反向源文件仍保留在本目录 `models/` 下。

已有官方 DAB 原例完成运行的截图证据；尚无低压正反向稳态数值对照通过或 PLECS 原始波形导出。Demo 的保存/导出限制不通过其他接口绕过。

## 合法平台选择

- **PLECS Standalone 5.0.7**：无需 MATLAB、账号或许可证即可按官方提示进入受限 Demo，支持界面新建模型、打开官方签名示例并运行；实际 5.0.7 提示禁止打开未签名自建文件、保存模型、导出和使用 PLECS Spice。完整试用许可通常为 30 天，申请涉及本人信息，不代申请。[官方下载](https://www.plexim.com/download/standalone)、[官方 Demo 说明](https://docs.plexim.com/plecs/5.0/before-you-begin/)、[官方试用](https://www.plexim.com/trial)
- **MATLAB + Simulink**：现有 [`build_dab_sps.m`](../../../scripts/matlab/build_dab_sps.m) 仅需这两个组件，无需 Simscape、Simulink Coder 或硬件支持包。本机未找到 MATLAB；脚本没有已验证的最低版本，不能把 API 静态核对当作版本运行兼容证明。[既有工程说明](../../../docs/SIMULINK.md)
- **MATLAB Online (basic)**：官方当前提供每月 20 小时免费额度，包含 MATLAB 和 Simulink，需 MathWorks 账号；因此不一定需要购买许可证。账号登录/关联由用户处理，Online 环境中的实际脚本兼容性仍需运行。[官方版本与额度](https://www.mathworks.com/products/matlab-online/matlab-online-versions.html)
- **PSIM**：当前官方 Altair One 试用下载需要账号及试用获取流程，未找到可核实的免身份官方下载运行路径，不代注册或申请。[官方试用流程](https://help.altair.com/altairone/topics/marketplace/application_try_free.htm)

有 MATLAB + Simulink 的本机在仓库根目录执行：

```powershell
matlab -batch "addpath(fullfile(pwd,'scripts','matlab')); build_dab_sps(true)"
```

MATLAB Online 中把仓库放入工作目录后执行：

```matlab
addpath(fullfile(pwd, 'scripts', 'matlab'));
outputDir = build_dab_sps(true);
```

`-batch` 为 MathWorks 官方非交互入口；代码输出会进入新的 `.runs/` 目录。以上命令尚未在 MATLAB 执行。MATLAB Runtime 或 Octave 不能代替这里所需的 Simulink 建模和 `sim` 执行。[官方批处理入口](https://www.mathworks.com/help/matlab/ref/matlabwindows.html)

本轮继续在 Demo 界面新建低压等效模型时，画布输入一度落到覆盖它的 Secondary 示波器，已定位为焦点问题。库到模型的跨窗口拖拽被界面工具以目标超出窗口范围拒绝，未执行。校正焦点后，界面工具收到用户物理 Escape 停止信号，所有 GUI 随即停止；新模型仍为空白，没有正反向结果。官方原例的 0.8 s 结果保留，未删除文件、绕过签名或导出限制。

独立平台对照已补充：同参数 ±30° 两源 R-L 电路已在 LTspice 从 0 A 实际积分 120 周期，两个方向均取得持续周期功率和完整末周期数据，见[仿真数值与解析对照](../spice_rl/README.md)。这是独立仿真，不代表此处自建 PLECS 模型已加载或运行。

本轮明确恢复后仍遇到 WSLg 按键与截图同步问题，随后工具再次报告物理 Escape 停止。已完成[官方原生 Windows 版文件准备](../../../verification/tooling/plecs-windows-20261106/README.md)，未运行安装器或启动新界面；下一次恢复后先验证原生输入。
