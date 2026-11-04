# 逐包 Simple S2MM 接收流程

`simple_s2mm.c/.h` 是固定 7 字/28 字节一帧的可移植 C11 接收核心，复用原有 `frame_validator`。单调用者、一个预先分配并映射的缓冲区、一次只在途一个包；没有线程、动态分配、描述符环或 Linux 驱动实现。平台只提供重启、设备同步、CPU 同步、提交和单次状态查询五个操作。

## 已执行的验证

2026-11-04 使用 Icarus Verilog 13.0 重新运行现有顶层，接收 **12 帧、84 字、336 字节**，第 137 周期完成采集，随后检查 5 周期背压保持。实际 CSV 序列化后用于原校验器的 16 项测试及本步 13 项接收流程测试。WSL Ubuntu-22.04 / GCC 11.4.0 使用 `-std=c11 -Wall -Wextra -Werror -Wpedantic`、AddressSanitizer、UBSan；全部通过，编译和执行退出码均为 0。

- [接收流程结果](../results/simple_s2mm/summary.json)、[13 项故障矩阵与有限调用轨迹](../results/simple_s2mm/fault_matrix.csv)、[编译日志](../results/simple_s2mm/c_compile.log)、[运行日志](../results/simple_s2mm/c_test.log)。
- [本次实际 RTL 轨迹](../results/simple_s2mm/capture/rtl_capture.csv)、[原校验器 16 项结果](../results/simple_s2mm/capture/fault_matrix.csv)。
- [主机测试源码](../tests/test_simple_s2mm.c)、[运行入口](../scripts/run_simple_s2mm.py)。

主机后端只是可控的操作回调：成功 payload 取自此次 RTL 捕获，完成/错误/长度/重启结果由测试注入。CPU 视图在提交前填入无效内容，直到完成后的 CPU 同步才复制暂存 payload；过早校验会失败。测试同时核对回调顺序和次数，没有实现 AXI DMA 寄存器或 cache 行为仿真，不能证明 cache 一致性、DMA、DDR 或板端联通。

| 测试 | 实际结果及检查 |
| --- | --- |
| 连续 12 包 | 12 次提交，每次 28 字节；验证 84 字、12 帧；设备同步 12 次、CPU 同步 13 次（含启动重启后一次） |
| 最后一次轮询才完成 | 每包第 3 次查询完成，正常接收，不误判超时 |
| 零长度、短包 24、超容量报告 32 | 第三包被拒绝，已验证 14 字；不对坏包做 CPU 同步或读取 |
| DMA 错误与完成同时报告 | 错误优先，保留 `raw_status=0x4052`，不读 payload |
| 一直未完成 | 第三包恰好查询 3 次后返回 TIMEOUT，保留设备所有权 |
| 超时后重启失败 | 保留原 TIMEOUT、已接受字数和状态证据；不做 CPU 同步 |
| 再次显式重启成功 | 确认停止后交回 CPU，清校验周期，从帧 0 重放真实 RTL 数据，12 帧通过 |
| 校验失败 | 只改真实第三帧的一个字节；索引错误位置为全局第 16 字，错误锁存 |
| 提交失败 | 不进入轮询，不回收缓冲区，显式重启前禁止复用 |
| 提前结束 | 仅接收一帧后按目标 12 帧 finish，报截断 |
| 无先前错误时重启失败 | 返回 RESTART_ERROR，缓冲区保留设备所有权 |

上表三种长度合计 3 项，总计 13 项。每项均检查再次 receive/finish 不增加平台调用、不覆盖第一错误证据；完成后再次调用同样不新增接收。轨迹字符：`R` 重启、`D` 交给设备、`S` 提交、`P` 单次状态查询、`C` 交给 CPU。成功路径为 `RC` 加 12 个 `DSPPC`。

32 字节是**注入的错误长度报告**，后端没有往 28 字节数组越界写入。真实超长包可能已造成不符合容量要求的传输；软件事后检查不能保证阻止物理越界。当前硬件设计的源每 7 字 TLAST，所以最大预期包应为 28 字节。

## 状态与所有权

1. `s2mm_init` 只设置内存状态，返回 NEEDS_RESTART，不碰硬件。一个实例只初始化一次，不能重新 init 来绕过在途缓冲区或锁存错误。
2. 显式 `s2mm_restart` 要求平台在有限次数内确认 DMA 停止并让 source/FIFO 回到帧 0；成功后才做 CPU 同步和 `fv_reset`。首次采集同样需要这个明确的周期边界。
3. 每次 `s2mm_receive_frame` 先做设备同步，再提交 28 字节；期间 CPU 不得访问、释放或重新分配该缓冲区，包括与其共用 cache 行的对象。
4. 每次状态查询先判断错误，再判断完成。只有无错误、完成且实际长度恰好 28 时才交回 CPU，并把该包 feed 给同一个校验器。不会每包 reset。
5. `s2mm_finish(&rx, 12)` 使用调用方原定帧数；成功返回 DONE 并终止本周期。异常锁存；不会自动丢包、重发、重置或硬件重跑。

DMA/提交/超时/长度失败时，`owner=DEVICE` 表示 CPU 仍无权访问；即使短包已报告完成，也先隔离到显式重启。校验失败发生在合法完成及 CPU 同步后，所以缓冲区归 CPU，但错误仍锁存，不能自动继续提交。

`poll_limit` 是每包最大状态查询次数，也是传给重启操作的上限；主机测试用 3 次。它不是毫秒或板端超时测量。有限退出依赖平台每个 MMIO/cache/重启回调本身能够返回，不能解决总线访问永久挂起；今后硬件平台若要求按时间截止，应采用其真实计时设施并测量，而不能把轮询次数写成虚构时长。

错误证据在 `status`、`last_event`、`last_polls`、`validator` 中。重启失败通过 `restart_failed` 补充记录，已有第一错误不被覆盖。显式重启成功会清掉旧周期证据，因此调用方应先保存这些字段，再按已有硬件恢复授权决定是否重启；本次只在主机后端执行重启流程。

## Standalone 接入草稿

[standalone_s2mm_draft.c](standalone_s2mm_draft.c) 和 [头文件](standalone_s2mm_draft.h) 调用仓库现有 AMD 驱动 API，**未编译、未链接 BSP、未上板**，不属于本次严格编译通过的文件。

- 接受调用者已经依据真实 BSP 初始化的 `XAxiDma`，以及独立提供的 CPU 指针、DMA 地址、完整专用缓冲区大小；没有 `xparameters.h` 替代物、硬编码基址、DDR 地址或 cache 行大小。
- 草稿限定当前工程的 Simple、非 Micro、仅 S2MM、32 位、无 DRE 配置。DMA 地址需满足字对齐；CPU 分配的起点/跨度还必须按实际 BSP cache 行对齐并独占，完整分配至少容纳 28 字节，不能把通用 28 字节栈数组直接当板端 DMA 缓冲区。
- 提交前调用 `Xil_DCacheFlushRange`；完成并经长度检查后调用 `Xil_DCacheInvalidateRange`。传入完整专用分配跨度，避免在部分 cache 行中共享别的数据。CPU 在设备拥有期间不读写该区域。ARMv8 此版本的 cache API 实现涉及 clean+invalidate，尤其不能让脏 CPU 行在 DMA 写入后覆盖结果。
- 提交前只清旧 IOC，错误状态保留。`XAxiDma_SimpleTransfer(..., XAXIDMA_DEVICE_TO_DMA)` 设置目的地址、RS，最后写长度启动；查询同时看错误与 IOC/Idle，完成后读实际 S2MM_LENGTH。
- 重启使用 `XAxiDma_Reset` 和有界 `XAxiDma_ResetIsDone` 查询；软复位作用于整个 DMA，所以草稿不允许共享 MM2S。source/FIFO 周期重置依赖 [现有 Tcl 的流侧复位连线](../vivado/README.md)，其传播及首字行为仍需完整 Vivado/IP 验证。草稿不能自行证明该前提。

未来板端使用前还需真实 BSP/工具版本匹配、地址映射与存储属性、完整缓存跨度、驱动初始化、复位传播、MMIO 与缓存调用的顺序保证及实际超时参数。这里没有 Linux 第二实现；Linux 只用于核对所有权与 DMA API 语义，主机回调不能代替内核驱动。

## 官方依据

核对日期：2026-11-04。只采用 AMD 原源和 Linux 官方文档：

- [PG021 Simple DMA](https://docs.amd.com/r/en-US/pg021_axi_dma/Direct-Register-Mode-Simple-DMA)：长度最后写入；目的地址及对齐要求；完成事件。一帧 TLAST 对应一个接收包，336 字节离线文件不能视为一次硬件 DMA 接收。
- [PG021 S2MM_LENGTH](https://docs.amd.com/r/en-US/pg021_axi_dma/S2MM_LENGTH-S2MM-DMA-Buffer-Length-Register-Offset-58h)：请求容量至少覆盖最大预期包，完成后更新实际写入长度；容量小于包长的结果不受保证。
- [PG021 S2MM_DMASR](https://docs.amd.com/r/en-US/pg021_axi_dma/S2MM_DMASR-S2MM-DMA-Status-Register-Offset-34h)：IOC 的完成/写 1 清除语义、Idle 与错误字段；不能只检查忙状态。
- [PG021 S2MM_DMACR](https://docs.amd.com/r/en-US/pg021_axi_dma/S2MM_DMACR-S2MM-DMA-Control-Register-Offset-30h)：停止可能终止流，软复位影响整个 DMA；不能只写停止位就立即回收缓冲区。
- [本地原厂驱动](../vendor/embeddedsw-xilinx_v2025.1/XilinxProcessorIPLib/drivers/axidma/src/xaxidma.c) 与 [原厂轮询示例](../vendor/embeddedsw-xilinx_v2025.1/XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c)：SimpleTransfer 参数检查、寄存器顺序、Reset/ResetIsDone 及缓存调用；原文件未改。
- [AMD Standalone ARMv8 cache 源码，xilinx_v2025.1](https://github.com/Xilinx/embeddedsw/blob/xilinx_v2025.1/lib/bsp/standalone/src/arm/ARMv8/64bit/xil_cache.c)：实际 cache API 行为；本次没有下载或伪造完整 BSP。
- [Linux DMA mapping guide](https://docs.kernel.org/core-api/dma-api-howto.html)：CPU 与 DMA 地址区分，streaming 映射的 CPU/device 同步和 cache 行隔离。不能直接把 CPU 指针当 DMA 地址。

## 复现

从本实验根目录执行；新输出目录可保留当前证据：

```powershell
& 'E:\python.exe' .\scripts\run_simple_s2mm.py --output results/simple_s2mm_recheck
```

入口先调用既有 `run_frame_validator.py` 得到新的真实 RTL 捕获并运行原 16 项测试，再严格编译和执行新增 13 项。需要已有 Icarus、Python 和 WSL/gcc；不会安装工具或访问硬件。`--iverilog`、`--wsl-distro` 可选择现有工具，Linux 上直接使用已有 gcc。日志只保存这次有限测试的调用轨迹，不记录无限轮询。
