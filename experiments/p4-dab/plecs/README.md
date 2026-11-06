# P4 原生 PLECS 工程准备与真实平台状态

**状态（2026-11-06）：已生成原生模型输入并启动官方 PLECS 5.0.7；尚未进入 Demo、解析/编译模型或运行仿真。** 首次窗口读取返回 `Computer Use app approval timed out`，因此没有点击 Demo、取得模型截图、产生 PLECS 波形或 PLECS 数值结果。下面的数值全部是独立解析期望值，不是 PLECS 输出。

## 文件

- `build_models.py`：独立编写的原生 PLECS 输入生成器，无 RPC、仿真结果读取或导出功能。
- `models/dab_sps_forward.plecs`：+30° 正向 SPS 原生输入。
- `models/dab_sps_reverse.plecs`：−30° 反向 SPS 原生输入。
- `reference_rl.py`：仅用 Python 标准库计算分段恒压 R-L 解析参考；不读 PLECS 进程或数据。

这些 `.plecs` 文件是新编写的模型源文件，不是从 Demo 保存或导出的文件。实际格式兼容性、连接和运行仍需 PLECS 检查。端口编号已按官方 5.0.7 包内组件及示例源码核对，包括 SignalMux 的输出端口 1、输入端口 2/3；这不替代原生解析和仿真。

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

已出现窗口 `PLECS (Ubuntu-22.04)`，但应用操作审批超时。窗口启动参数曾指向第一版草稿；权限恢复后请明确打开下面的最终输入，不使用 `models_01` 草稿：

```text
/mnt/e/UserData/Documents/ChatGPT/硬件/experiments/p4-dab/plecs/models/dab_sps_forward.plecs
/mnt/e/UserData/Documents/ChatGPT/硬件/experiments/p4-dab/plecs/models/dab_sps_reverse.plecs
```

后续最少步骤：

1. 恢复该应用的 computer-use 操作权限，或由用户自行选择 PLECS 的 `Run in demo mode`。
2. 用 `File > Open` 打开上述正向模型，执行 `Simulation > Start`；如出现解析或电路错误，先保留可见错误和模型源，再修复。
3. 运行完成后核对终止时间 0.006 s、三个示波器信号和四个 Display；再打开反向模型执行相同检查。仅可见结果应明确标注为人工/界面观察。
4. 需要完整可复核波形和数据文件时，提供合法 PLECS Standalone 完整/试用许可，再使用官方导出功能。Demo 模式禁止保存模型和数据；不使用脚本、内存、剪贴板或 RPC 绕过该限制。

## 合法平台选择

- **PLECS Standalone 5.0.7**：无需 MATLAB、账号或许可证即可按官方提示进入受限 Demo，支持建模和运行，禁止保存模型/数据。完整试用许可通常为 30 天，申请涉及本人信息，不代申请。[官方下载](https://www.plexim.com/download/standalone)、[官方 Demo 说明](https://docs.plexim.com/plecs/5.0/before-you-begin/)、[官方试用](https://www.plexim.com/trial)
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
