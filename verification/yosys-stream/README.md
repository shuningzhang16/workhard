# 通用综合与同一激励重放

2026-11-04，本机在 WSL Ubuntu 22.04 运行 Yosys 0.9，对 `daq_stream_top` 的 `FRAME_WORDS=7`、`FIFO_DEPTH=3` 进行实际通用综合。随后用 Icarus 分别运行原 RTL 和生成的网表，两次均接收 84 个字，逐行比较 CSV 的全部字段（周期、数据、TKEEP、TLAST）一致。`check -assert` 报告 0 个问题。

执行入口是 [check_synthesis.py](../../scripts/check_synthesis.py)。网表已经展开参数，因此脚本仅移除测试平台实例上的参数覆盖；激励和检查保持不变。此次只验证该参数组合和有限测试序列，不属于形式等价证明。

Yosys 统计为 590 个通用单元：150 个 DFF、297 个 MUX、59 个 AND、27 个 OR、48 个 XOR、9 个 NOT。未执行 ABC 或目标器件映射，不能把这些数字当成 FPGA LUT/FF 资源、Fmax 或时序收敛结果。Icarus 对生成网表缺少 timeunit 的警告保存在编译日志；此处运行的是零延迟逻辑仿真。

## 证据

- [成功运行汇总](run2/summary.json)、[综合日志](run2/synthesis.log)、[综合命令](run2/synthesis.ys)。
- [原 RTL 接收记录](run2/rtl/rtl_capture.csv)、[网表接收记录](run2/mapped/rtl_capture.csv)、[生成网表](run2/daq_stream_mapped.v)、[网表结构](run2/netlist.json)。
- [首次失败](run1/yosys-version.log)：隔离目录缺少 `libtcl8.6.so`。保留错误后，将 Ubuntu 的 `libtcl8.6` 解压到同一工具目录，通过进程级 `LD_LIBRARY_PATH` 运行成功。没有修改系统安装或系统 PATH；下载记录见本目录两个 setup 日志。

## 重现

Ubuntu 已安装 Yosys 与 Icarus 时，在仓库根目录运行：

```sh
python3 scripts/check_synthesis.py
```

本机 Windows 使用仓库内忽略的 `.tools/yosys` 和 P2 的 Icarus，运行：

```powershell
E:\python.exe -X utf8 scripts/check_synthesis.py
```

首次准备本机 Yosys 时，在 WSL 的仓库根目录执行下列命令，每步成功后再执行下一步：

```sh
mkdir -p .tools/yosys-debs .tools/yosys
cd .tools/yosys-debs
apt-get download yosys=0.9-2 libtcl8.6=8.6.12+dfsg-1build1
dpkg-deb -x yosys_0.9-2_amd64.deb ../yosys
dpkg-deb -x libtcl8.6_8.6.12+dfsg-1build1_amd64.deb ../yosys
```

默认输出写入新的 `.runs/yosys-*` 目录，包含命令、退出码、编译输出和两份原始轨迹。GitHub 的 P2 任务使用 Ubuntu 24.04 软件源提供的 Yosys，并记录该次实际版本；单元数量可能随版本变化，检查依据是综合合法性及两条轨迹一致。此检查没有执行 Vivado、DMA/DDR 或任何硬件操作。
