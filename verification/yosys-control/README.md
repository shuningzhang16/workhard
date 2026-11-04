# 控制寄存器 wrapper 的综合后重放

在 `daq_axi_lite` 的实际 RTL 测试通过后，用同一组 AXI-Lite/Stream 激励重放 Yosys 通用综合网表。参数仍为 7 字一帧、FIFO 深度 3；Yosys 0.9、未使用 ABC 或目标器件映射。

运行命令（仓库根目录）：

```powershell
E:\python.exe -X utf8 scripts/check_synthesis.py --control
```

Ubuntu 安装 Yosys/Icarus 后使用 `python3 scripts/check_synthesis.py --control`。本机工具准备方式沿用 [stream 综合记录](../yosys-stream/README.md)。

原 RTL 和网表都运行了 23 次写、46 次读，接收 70 字/10 帧。两者逐行比较的 457 行 stream 周期记录、161 行 AXI 总线握手记录一致；测试平台同时核对 AW/W 独立到达、B/R 背压稳定、帧边界停止和重启。

Stream 的周期号、valid/ready 和计数始终比较。仅在 TVALID=0 时忽略无效载荷的 data/keep/last；原始 CSV 未修改。有效拍包括被反压的拍，全部字段必须一致。AXI 总线记录全部字段比较。生成网表已展开参数，测试平台只移除实例的参数覆盖，其他激励及检查不变。

[结果汇总](run1/summary.json)记录 1,716 个通用单元；[RTL 汇总](run1/rtl/summary.json)和[网表汇总](run1/mapped/summary.json)记录实际事务数量。[综合日志](run1/synthesis.log)、[原 RTL 轨迹](run1/rtl/stream_cycles.csv)、[网表轨迹](run1/mapped/stream_cycles.csv)及总线 CSV 全部保存。

该结果覆盖当前有限激励与参数组合，不是形式等价证明。通用单元数不代表 ZCU104 LUT/FF 资源；未生成 bitstream、执行器件时序分析、验证 PS 地址映射或运行硬件。生成网表的 timeunit 警告仍保留在日志中，这里是零延迟逻辑仿真。
