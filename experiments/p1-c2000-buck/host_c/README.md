# 主机 C 采样控制：四工况逐拍对照

后续已完成 [C 与 Python 各自驱动 PWM 的闭环对照](CLOSED_LOOP.md)：原 C 核心经共享库实际闭环调用 36,006 次，覆盖三个正常场景及三种故障/显式恢复，独立 C/Python 轨迹一致。量化清除盲区及周期内峰值超出 10% 的结果仍保留。下文继续记录之前的固定 CSV 回放阶段，不替代新的闭环证据。

`buck_control.h/.c` 是独立 C11 模块，重写本实验 `VoltagePI` 与 `ProtectedController` 的采样语义。只包含数值控制与状态，不引用 TI 原厂代码，不访问 ADC、PWM、Trip 或其他外设。模块无动态内存分配、文件操作及平台调用；文件读取与验证工具在独立程序中。

本轮在 Linux x86_64、GCC 11.4.0 上实际通过严格警告编译，并在 ASan/UBSan 下运行边界检查和四工况回放。共 **26,004 个采样点**；C 与即时 Python 计算、原 PWM CSV 的 duty/reference 最大绝对差均为 **0**，状态、活动故障、锁存原因、清除结果逐拍精确一致。

验证入口支持 Windows Python 调用 WSL GCC，以及 Linux Python 直接调用原生 GCC。两条入口均已在本机执行：Windows Python 3.14.4→WSL Ubuntu 22.04，以及同一 Ubuntu 22.04 内的 Python 3.10→原生 GCC。随后 Ubuntu 24.04 的 GitHub CI 也实际通过，运行和证据见 [统一 CI 记录](../../../docs/CI.md)；下文工具版本及零差值表描述本机执行结果。

## 固定参数与接口

参数直接写在头文件中，没有新增运行时配置框架。

| 参数 | 固定值 |
|---|---:|
| 采样周期 | 20 µs |
| PI Kp / Ki | 0.03 / 30 |
| 占空比上下限 | 0 / 0.95 |
| 目标电压、软启动 | 2 V、20 ms（1,000 拍） |
| 过流 | `abs(iL) >= 2.5 A` |
| 输出过压 | `vO >= 2.4 V` |
| 输入欠压 | `Vin <= 6 V` |
| 清除的残余状态上限 | `abs(vO) <= 0.1 V` 且 `abs(iL) <= 0.1 A` |

`buck_controller_init()` 初始化调用者拥有的 `BuckController`。此后按从零开始的连续采样序号调用 `buck_controller_step()`，输入有限的 SI 单位测量值，每个 `clear_request=true` 代表一次显式请求。函数返回 `BuckCommand`；不会替调用者采样、安排执行时刻或写入硬件。

`buck_voltage_pi_step()` 也可单独使用，其积分器用 `BuckVoltagePI pi = {0}` 初始化。PI 保持原来的条件积分：候选输出越过上限且误差为正，或越过下限且误差为负时，不接受本拍积分增量；最终占空比再限制到 0–0.95。反向误差可以继续积分以退出饱和。

状态枚举为 SOFT_START=0、RUN=1、FAULT_LATCHED=2。活动故障用位表示：过流=1、输出过压=2、输入欠压=4，多个原因可以同时存在。首次锁存原因保持不变，后续活动原因独立更新。清除结果枚举为 not_requested=0、rejected_active_fault=1、rejected_residual_energy=2、accepted=3、ignored_not_latched=4。

顺序与 Python 一致：先检测并锁存，再处理本拍清除请求，再计算参考和 PI。锁存输出为零；没有显式清除时不会自动恢复。清除成功先重置积分器和软启动起点，然后仍在同一拍运行 PI，因此负的残余输出电压可能产生极小正占空比，积分器也可能立即得到本拍增量。这一行为未改成“清除拍强制输出零”。

接口以有限测量值和连续采样调用为使用前提；本轮没有新增 ADC 失效处理或调度适配。

## 实际回放方法和结果

C 回放程序直接读取已有 `simulation/protected_switching_results/*_control_samples.csv`。它使用 Vin、vO、iL、clear_request 四项真实测量/命令列驱动控制器，校对 CSV 时间与行序对应的 20 µs 采样时刻；原 CSV 的 duty、reference、state、fault、clear_result 均不作为 C 算法输入。

Python 验证程序对同样的测量和清除请求重新调用现有 `ProtectedController`，同时读取原 CSV 的期望结果。C 输出与这两个参照逐拍比较，完整结果保存到 `*_comparison.csv`。没有重新生成或覆盖原 PWM 数据，也没有用 C 输出重新驱动功率级。

| 工况 | 采样点 | 最大 duty 差 | 最大 reference 差 (V) | 不匹配行数 |
|---|---:|---:|---:|---:|
| 正常负载阶跃 | 5,001 | 0 | 0 | 0 |
| 过流 | 7,001 | 0 | 0 | 0 |
| 输出过压 | 7,001 | 0 | 0 | 0 |
| 输入欠压 | 7,001 | 0 | 0 | 0 |

以上数字对“C 与即时 Python”和“C 与已保存 CSV”两组比较均成立。两个运行入口的结果也相同。Windows/WSL 入口本次用时约 7.63 s，Linux 原生入口约 4.18 s，包括编译、运行、比较与导出；这些总耗时不能用作 ISR 执行时间。

浮点比较使用绝对容差：duty 为 **1e-11**，reference 为 **1e-14 V**。实测 `sizeof(double)=8`、`FLT_RADIX=2`、`DBL_MANT_DIG=53`，即 binary64 的 ε≈2.220446×10⁻¹⁶。以最长 7,001 拍、单位量级上的约四次基础运算估算审阅尺度，`4×7001×ε≈6.22×10⁻¹²`，取 1e-11 作为 duty 舍入余量；参考斜坡只有少量乘除且最大 2 V，取 1e-14 V。它们是工程舍入余量，**不是严密的累计误差上界**，不改动故障阈值、原功率级判据或离散结果的精确比较。

构建关闭 fast-math 和浮点乘加收缩，保留与 Python 对应的运算顺序。本机结果恰好为零差值，不能据此推断其他编译器、精度、优化选项或 C2000 目标会逐位一致。

## 边界与编译检查

边界可执行程序验证三组有限场景：

- 9 个阈值向量：正负过流的精确阈值及相邻未越限浮点数、输出过压和输入欠压的精确/相邻值、三故障同时出现。
- 锁存与清除：首次原因保持、持续故障下拒绝、无自动清除、±0.1 附近残余状态的严格边界、边界值允许清除，以及恢复后的第 999/1,000 拍软启动状态。
- PI：上下限饱和时保持积分器，误差方向反转后恢复积分。

实际编译选项如下；两个可执行程序均启用 ASan 和 UBSan，运行时启用泄漏检测及遇错终止：

```text
-std=c11 -O1 -g3
-Wall -Wextra -Wpedantic -Wconversion -Wshadow
-Wstrict-prototypes -Wmissing-prototypes -Werror
-fno-fast-math -ffp-contract=off -fno-omit-frame-pointer
-fsanitize=address,undefined
```

所有编译及执行退出码为 0，没有编译警告或 sanitizer 报告；不是仅检查源码或只生成构建命令。边界检查和每个回放分别启动启用 sanitizer 的实际 C 进程。

初始只读环境探测发现登录 shell 的 PATH 选择了用户目录中不可执行的 `uname`，原始输出已保存到 `evidence/host-c-tool-probe.txt`。验证进程使用 `/usr/bin/gcc`、`/usr/bin/uname`，并只在子进程内设置 `PATH=/usr/bin:/bin`，没有修改系统环境或安装工具链。C 编译、边界和回放没有发生失败。

## 复现与输出位置

Windows，从 P1 目录执行：

```powershell
& 'E:\python.exe' .\host_c\run_validation.py --output host_c/results
```

Linux / GitHub Ubuntu runner，从 P1 目录执行：

```bash
python3 host_c/run_validation.py --output .tools/host-c-ci-results
```

也可以从其他工作目录用脚本完整路径调用。`--output` 默认是 `host_c/results`；相对路径始终相对 **P1 实验目录**，绝对路径也必须位于 P1 内。参数控制所有 CSV、指标、参数和命令日志的输出位置，便于统一脚本和 CI 保留独立结果。编译产物始终位于已忽略的 `.tools/host-c/`；当前入口按顺序运行，不为同一工作目录内的并发构建安排隔离目录。

原生 Linux 入口在本机实际运行的命令为：

```powershell
wsl -d Ubuntu-22.04 -- /usr/bin/env PATH=/usr/bin:/bin /usr/bin/python3 host_c/run_validation.py --output .tools/host-c-native-validation
```

可提交清单：

- `host_c/buck_control.h`、`buck_control.c`：独立控制模块与固定参数。
- `host_c/replay_csv.c`、`test_boundaries.c`、`run_validation.py`：回放、边界及统一入口。
- `host_c/README.md`：本说明。
- `host_c/results/`：四份 C 输出、四份完整比较、`metrics.json`、`parameters.json`、`commands.json`，共 11 个文件，约 5.84 MB。命令日志含实际参数、退出码、stdout/stderr 和工具版本。
- `evidence/host-c-validation.txt`、`host-c-native-validation.txt`、`host-c-tool-probe.txt`：两个入口的完整运行日志及初始环境探测记录。
- `evidence/host-c-native-validation/`：原生入口的命令、指标、参数 JSON；重复的完整 CSV 留在本地忽略的 `.tools/host-c-native-validation/`。
- P1 `README.md`：阶段入口和结果摘要。

这里验证的是**主机 C 采样逻辑与已有 Python 轨迹的相符性**。没有编译或烧录 C2000，没有验证 ISR 周期、ADC/PWM 更新延时、Trip 硬件或功率级安全；既有理想续流模型的负压和反向电流边界仍然存在。原厂受限文件、平均模型、PWM、ngspice 结果保持独立。
