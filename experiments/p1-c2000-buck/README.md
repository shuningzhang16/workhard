# P1：TI C2000 Buck 学习与独立平均模型

更新日期：2026-11-04。

当前完成两步：原厂版本来源与许可核对，以及**独立教学 Buck 平均模型的可执行仿真**。原厂源码未修改。所有新增仿真均不读取或复制 TI 源码，不是原厂复现，也不是硬件测量。

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
