# P1：TI C2000 Buck 学习与独立平均模型

更新日期：2026-11-05。

当前完成原厂版本来源与许可核对、**独立教学 Buck 平均模型的可执行仿真**、采样式故障锁存与软启动恢复、九组 PI 的有限比较、真正 PWM 电压切换的理想开关模型、ngspice 独立瞬态对照、PWM 功率级中的保护与显式恢复、独立主机 C 控制模块的逐拍验证、禁用输出的 F280049C RAM 工程实际构建，以及一周期更新延迟与 ADC/PWM 量化的隔离仿真。原厂源码未修改。所有新增仿真均不读取或复制 TI 源码，不是原厂复现，也不是硬件测量。

## 最新完成：一周期更新延迟与 ADC/PWM 量化对照

详见 [隔离仿真及初学者说明](simulation/IO_TIMING.md)。复用原控制器和 PWM 功率级，对启动、负载阶跃、过压三个场景比较原时序与一周期 CMPA 延迟、12 位 ADC、2,000 计数 PWM 量化。负载采样点超调由 9.5743% 增至 9.9838%，恢复时间由 5.10 ms 增至 5.18 ms；细步长周期内超调为 10.0173%，没有把原采样检查通过扩展为周期内峰值通过。

发现明确的单极性 Vout 清除盲区：真实输出约 -1.907 V、储能约 0.854 mJ 时，量化测量为 0 V/0 A，复制的控制器会接受假想清除。主功率级未施加该命令，仍按 80 ms 显式清除。结果和局限均已留证，13 项测试通过；步长减半时 PWM 计数和状态不变。此实验不是测得的 ADC/ISR 延迟，目标固件仍保持 PWM 禁用与 Trip 锁存。

```powershell
& 'E:\python.exe' .\simulation\run_io_timing.py
& 'E:\python.exe' .\simulation\check_io_timing_refinement.py
```

## 已完成：F280049C 禁用输出的真实目标 RAM 工程

详见 [目标工程与代码执行路径](firmware/README.md)。已实际使用 cl2000 25.11.1.LTS 和官方 F28004x DriverLib 26.02.00.00.LTS 编译、链接独立固件，生成 C28x EABI ELF；共分配 4,358 个 16 位 RAM 字（含栈），Flash 分配为 0。实际目标对象确认 double 为 64 位、53 位尾数，14 个编译期常量与 Python binary64 差值均为 0；这不是目标运行时重放。

GPIO0/1 保持普通输入，ePWM One-Shot Trip 启动即锁存且没有解除路径。ADC、ePWM 与外部 Trip 使用已核实 DriverLib 接口，模拟前端标度和 GPIO 分配明确标为待板卡确认。原控制器和教学阈值不变。首轮入口诊断失败及隔离修复、最终命令与 map 均已留证；没有连接或烧录硬件，没有宣称 20 µs ISR 或硬件保护已验证。

```powershell
& 'E:\python.exe' .\firmware\build_target.py --output firmware/results
```

## 已完成：主机 C 控制模块与逐拍验证

详见 [主机 C 说明](host_c/README.md)。独立 C11 模块保持现有 PI、采样、保护阈值、锁存、残余状态拒绝与软启动语义。GCC 11.4 严格警告编译和 ASan/UBSan 实际运行均通过，四份 PWM CSV 的 26,004 个采样点与即时 Python 及已存结果逐拍一致：duty/reference 最大绝对差均为 0，离散状态、故障和清除结果无差异。

验证入口支持 `--output` 指定 P1 内输出目录，以及 Windows→WSL GCC 和 Linux 原生 GCC；两条入口已在本机 Ubuntu 22.04 环境完成实测。Ubuntu 24.04 的统一 CI 也已实际通过，见 [CI 记录](../../docs/CI.md)。结果和编译/执行命令在 `host_c/results/`，原生入口另有独立日志。此步仅验证主机 C 逻辑，未编译/烧录 C2000，也未验证 ISR 时序或 Trip 硬件。

```powershell
& 'E:\python.exe' .\host_c\run_validation.py --output host_c/results
```

## 已完成：PWM 功率级中的保护与显式恢复

详见 [PWM 保护说明](simulation/PROTECTED_SWITCHING.md)。复用原有保护控制器与全部阈值，故障时保持 L/C 状态并继续积分理想低侧续流支路。过流、输出过压、输入欠压分别在 50.32、50.30、50.00 ms 锁存；活动故障及残余储能条件下的清除按原规则拒绝，80 ms 显式清除后均在 30.50 ms 内恢复至目标 ±2%。首次开关节点阈值越过到采样检测约为 16.78–17.24、13.34–13.84、0 µs；欠压的零值来自刺激与采样同步。

正常负载阶跃与原 PWM 实现逐项一致。10 项测试通过，实际检查开关电压、L/C 连续性、储能耗散和恢复后的脉冲；原有条件未放宽。完整控制采样、周期统计及事件附近有限窗口保存于 `simulation/protected_switching_results/`，同时保留平均模型差异。首轮测试接口错误及隔离修复证据单独留存。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
& 'E:\python.exe' .\simulation\run_protected_switching.py
& 'E:\python.exe' -m unittest discover -s .\simulation -p 'test_*.py' -v
```

过压案例锁存后输出仍升至 2.529 V，并出现负压和反向电流；这是指定理想续流模型的实际结果，不是硬件保护保证。本轮保护工况只运行 Python，未把既有 ngspice 固定占空比结果扩展为保护验证。

## 已完成：真实 ngspice 瞬态独立对照

详见 [SPICE 对照说明](simulation/SPICE_COMPARISON.md)。WSL Ubuntu-22.04 中从 Ubuntu 官方源下载约 2.35 MB 的 ngspice 包，仅解压到本地忽略的 `.tools/`，未安装至系统。已实际运行原固定占空比网表及稳态/启动探针，使用 `IC=0` 和 `uic` 对齐 Python 的零初始电压、电流，没有用默认 DC 工作点代替启动。

约 59.6–60 ms 窗口内，SPICE 与 Python 的输出均值均约为 2 V；输出峰峰纹波分别为 0.751888、0.752198 mV，相对差 -0.041231%；电感峰峰纹波相对差 -0.005337%。8 项对照检查通过，命令、版本、原始日志和有限波形位于 `simulation/spice_results/`。这些结果只覆盖理想固定占空比案例，LTspice 未运行。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
& 'E:\python.exe' .\simulation\run_spice_comparison.py
```

## 已完成：PWM 开关模型证据

详见 [开关模型说明](simulation/SWITCHING.md)。Python 标准库实现 50 kHz 真实 0/9 V 电压切换，精确按 PWM 边沿分段积分，保留有符号电感/电容状态。固定 D=2/9 的稳态周期均值约 2 V，输出峰峰纹波约 0.752145 mV，电感峰峰纹波约 0.141422 A，与基本解析关系接近。

默认 PI 的负载阶跃采样点超调为 9.5743%，恢复至 ±2% 为 5.10 ms。积分最大子步从 0.5 µs 减至 0.25 µs 后，输出纹波估计变化约 0.25%，控制周期仍为 20 µs。新增有限窗口开关波形、完整周期统计及平均模型对照保存在 `simulation/switching_results/`；原平均模型结果没有覆盖，共 8 项测试通过。此处指标来自 Python；后续 ngspice 固定占空比结果单独记录在上一节。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
& 'E:\python.exe' .\simulation\run_switching.py
& 'E:\python.exe' -m unittest discover -s .\simulation -p 'test_*.py' -v
```

## 已完成：有限 PI 比较与数值检查

详见 [九组比较说明](simulation/PI_COMPARISON.md)。9 组中有 3 组满足全部现有条件，所有候选及未满足项均已保存。按最差扰动偏差优先的排序，Kp=0.06、Ki=45 将偏差从 0.469224 V 降至 0.398954 V（减少 14.98%），但最差扰动恢复从 13.98 ms 增至 14.44 ms，输入阶跃超调也增加。默认 Kp=0.03、Ki=30 保持不变，没有全局最优或硬件性能的声明。

固定控制周期 20 µs，仅将 RK4 积分步长从 5 µs 减至 2.5 µs：原设置和候选的六次轨迹比较最大电压差为 1.15315e-9 V，恢复指标均未变化。完整三工况候选 CSV、双步长轨迹和指标差已保存；原有 6 项回归测试通过，保护实现和条件未改动。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
& 'E:\python.exe' .\simulation\compare_pi.py
& 'E:\python.exe' -m unittest discover -s .\simulation -p 'test_*.py' -v
```

## 已完成：采样保护与恢复

详见 [保护模型说明](simulation/PROTECTION.md)。新增教学假设的过流、输出过压、输入欠压检测；故障锁存，明确拒绝/接受清除命令，清除后重新软启动。三个故障工况在 50.32、50.30、50.00 ms 锁存，80 ms 显式清除后，分别在 30.48、30.50、30.50 ms 内恢复至目标 ±2%。正常三工况没有误触发，波形与第一步逐样本完全一致；原有测试未放宽，共 6 项测试通过。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
& 'E:\python.exe' .\simulation\run_protection.py
& 'E:\python.exe' -m unittest discover -s .\simulation -p 'test_*.py' -v
```

故障时继续积分理想低侧续流支路，允许反向电流及负电压，不把 `duty=0` 描述成真实硬件关断。清除要求检测条件恢复且状态回落到指定低储能范围；低阻负载的实际移除仍由测试器控制，采样正常不能证明短路已经消失。边界、阈值、原始 CSV、状态转换和能量检查均在上述说明及 `simulation/protection_results/` 中记录。

## 已运行的第一小步

详见 [独立平均模型说明](simulation/README.md)。Python 标准库实现理想功率级、离散电压 PI、最小软启动，已执行启动、负载阶跃、输入变化三个工况，每个工况保存 5,001 行完整控制采样数据。

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
& 'E:\python.exe' .\simulation\run_simulation.py
& 'E:\python.exe' -m unittest discover -s .\simulation -p 'test_*.py' -v
```

开环 `Vout=D×Vin` 的独立正确性检验及三个闭环工况自检通过。进入并保持在目标电压 ±2% 的恢复时间分别为 10.48、5.12、13.98 ms，启动时间从 20 ms 参考斜坡结束算起。负载阶跃最大超调 9.66%；输入阶跃最大绝对偏差 0.469 V。完整参数、误差与指标定义见说明和 `simulation/results/`，原始执行日志见 `evidence/simulation-run.txt` 与 `evidence/simulation-tests.txt`。

首轮积分增益偏小导致软启动跟踪检查失败，已保存原始代码、CSV 和失败日志，在隔离副本只调整积分增益后重新验证；未放宽测试条件。此步没有扩展保护、开关器件或效率模型，也未进行参数大扫描。

## 已取得的原始文件

官方版本：C2000Ware DigitalPower SDK **26.01.00.00**；Buck 例程 **TIDM_DC_DC_BUCK v2.01.05.00**。

本地文件保留 SDK 原目录，位于 `vendor/C2000Ware_DigitalPower_SDK_26_01_00_00/`。获取脚本实际取得 29 个文件，共 397,137 字节，包括：

| 原 SDK 路径 | 内容 |
|---|---|
| `solutions/tidm_dc_dc_buck/f28004x/buck/` | `buck_main.c`、配置头文件、CLA 入口、`Kit.json`、SysConfig 配置及器件启动文件 |
| `solutions/tidm_dc_dc_buck/f28004x/drivers/` | `buck_hal.c`、`buck_hal.h`，即 ADC、PWM 等器件配置 |
| `solutions/tidm_dc_dc_buck/source/buck/` | `buck.c`、`buck.h`、原厂调试脚本与波形窗口配置 |
| `solutions/tidm_dc_dc_buck/f28004x/ccs/` | powerSUITE 与 nonpowerSUITE 两个原厂 `.projectspec` |
| `solutions/tidm_dc_dc_buck/f28004x/cmd/` | 原厂 Flash 链接文件 |
| `license.txt`、`docs/manifest.html`、`.metadata/.tirex/package.tirex.json` | 当前 SDK 许可、组件软件清单及版本元数据 |

此外，本地保留了 Resource Explorer 入口的 `.metadata/.tirex/license/license.txt` 供对照。当前 Buck 组件的判断依据是软件清单与 SDK 根目录 `license.txt`。

目标芯片由两个 `.projectspec` 实际确认：**TMS320F280049C**。两个工程声明的 C2000 编译器版本均为 **22.6.0.LTS**，SysConfig 产品版本为 **1.21.0**。这些是工程声明值，不等于已经验证本机可编译。

## 本次 GitHub 上传范围与许可

官方 `docs/manifest.html` 的 `TIDM-DC-DC-BUCK_FIRMWARE Manifest Table` 将该例程标为 **TI_Commercial**，交付形式为 Source。SDK 根目录 `license.txt` 第 2.a(i) 节规定源码内部使用，第 2.g(i) 和 2.g(v) 节限制源码向第三方披露或提供。因此，本次**不将 TI Buck 原厂源码公开上传到 GitHub**，也不将它称为个人原创或 BSD 开源代码。

`vendor/` 已被本目录 `.gitignore` 排除，已用 `git check-ignore --no-index` 验证规则生效；不要以强制添加方式上传该目录。可提交的内容是独立教学模型及其结果、本说明、官方来源与下载记录、获取脚本。原厂版权、许可和源码内容在本地均保持原样，没有增加作者、署名或致谢。

## 来源与取得方法

- [TI TIDM-DC-DC-BUCK 官方入口](https://www.ti.com/tool/TIDM-DC-DC-BUCK)：设计指南、原理图、BOM、Gerber 和硬件组合入口。
- [TI DigitalPower SDK 官方入口](https://www.ti.com/tool/C2000WARE-DIGITALPOWER-SDK)：本次核对到的 SDK 版本为 26.01.00.00。
- [TI Resource Explorer 包元数据接口](https://dev.ti.com/tirex/api/packages)：确认版本及官方下载地址，所选条目保存在 `evidence/ti-package-list.json`。
- [TI 官方 SDK ZIP](https://downloads.ti.com/ccs/esd/tirex/zips/C2000Ware_DigitalPower_SDK_26_01_00_00/all/C2000Ware_DigitalPower_SDK_26_01_00_00__all.zip)：仅用 HTTP Range 读取目录和 Buck 所在片段，没有下载或安装整套 737,637,609 字节 SDK。
- [原厂主程序](https://dev.ti.com/tirex/content/C2000Ware_DigitalPower_SDK_26_01_00_00/solutions/tidm_dc_dc_buck/f28004x/buck/buck_main.c)、[软件清单](https://dev.ti.com/tirex/content/C2000Ware_DigitalPower_SDK_26_01_00_00/docs/manifest.html)、[SDK 许可](https://dev.ti.com/tirex/content/C2000Ware_DigitalPower_SDK_26_01_00_00/license.txt)：实际访问并核对。

官方 SDK 页面指向的 GitHub 仓库当时返回 404；TI 静态内容服务器对原厂 `.cmd` 文件返回 403。获取脚本据此改为读取同一公开 ZIP 的例程片段。失败记录保存在 `evidence/source-fetch-notes.txt` 与 `evidence/attempt1/`，没有关闭 TLS 验证或修改系统设置。

在具有相应 TI 使用权限的环境中，用标准 Python 复现本地获取：

```powershell
Set-Location 'E:\UserData\Documents\ChatGPT\硬件\experiments\p1-c2000-buck'
& 'E:\python.exe' .\fetch_original.py
```

本机已验证 `E:\python.exe` 为 Python 3.14.4；PATH 中的 `python` 指向一个缺少 `pyvenv.cfg` 的环境，因此此处使用实际解释器路径。脚本只依赖标准库，不执行原厂固件，也不改 Git 索引。

## 核对结果及限制

- `evidence/download-results.json`：29 个原始文件的官方 URL、HTTP 状态和实际字节数。
- `evidence/fetch-original-run.txt`：成功获取的原始执行输出。
- `evidence/verification.json`：29 个文件存在且长度与下载记录一致；两个工程 XML 和 `Kit.json` 均解析成功；版本与目标芯片已核对。
- `evidence/sdk-entries.json`：官方 ZIP 中与 Buck 相关的目录条目，用于按原路径取得子集。这里也列出了未下载的 powerSUITE 模板及计算表，实际取得的文件以 `download-results.json` 为准。

这是**源码子集，不是独立可编译 SDK**。未取得完整的 C2000Ware DriverLib、DCL、SFO、CLAmath、SFRA 库及 powerSUITE 工具；原厂工程仍引用这些依赖。未确认本机有 CCS/对应编译器，未编译或运行原厂工程。新增 Python 仿真的结果仅适用于独立教学模型。官方低压硬件组合为 BOOSTXL-BUCKCONV 与 LAUNCHXL-F280049C，本轮未连接或操作硬件。

原始来源记录与独立模型分步保存在 Git 历史中。后续可围绕扰动响应、保护逻辑和开关级模型继续逐项验证。
