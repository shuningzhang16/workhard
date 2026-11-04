# C 帧流校验器

`frame_validator.c/.h` 是独立 C11 模块，不依赖操作系统、动态内存、DMA 驱动或板级头文件。此次用 WSL Ubuntu-22.04 的 x86_64 GCC 11.4.0 实际编译执行；尚未进行 ARM 交叉编译或 PS 板端执行。

## API 与采集周期

| 调用 | 行为 |
| --- | --- |
| `fv_reset(&state, frame_words, first_frame)` | 开始明确的新采集周期，清计数及错误；指定帧长 1～65536 和第一帧序号，通常为 0 |
| `fv_feed(&state, bytes, byte_count)` | 按顺序接收一个批次，跨批次保留帧序号与字索引 |
| `fv_finish(&state, requested_frames)` | 在采集结束时检查尾帧与总帧数；不清除状态 |

调用者先 reset，再串行传入已完成的缓冲区，最后 finish。批次可结束于帧中间，但长度必须是 4 字节的整数倍；例如实际测试使用 1、5、2、11、3 字循环分批，帧长为 7。字由逐字节读取的小端编码组成：`uint32 = frame_sequence[15:0] << 16 | word_index[15:0]`，不依赖主机端序或 `uint32_t *` 强制转换。帧序号从 65535 自然回到 0。

任何错误都会锁存，后续 feed/finish 返回原错误且不继续接受数据；只能通过显式 `fv_reset` 开始新周期。reset 只操作校验器内存，不操作 PL、FIFO 或 DMA，也不能证明旧缓冲区已经安全释放。不要把每个 DMA 批次都当作新周期 reset。

| 状态 | 含义 |
| --- | --- |
| `OK` | 当前批次/结束检查通过 |
| `BAD_CONFIG` | 状态指针或帧长配置无效 |
| `BAD_LENGTH` | 非 4 字节整数倍的长度，或非空长度搭配空指针；本批次不被接受 |
| `WORD_INDEX` | 帧内字索引与预期不同 |
| `FRAME_SEQUENCE` | 字索引正确但帧序号不同 |
| `TRUNCATED` | 结束时仍有半帧，或完整帧少于调用者要求 |
| `FRAME_COUNT` | 结束时完整帧多于调用者要求 |

缺字、重复字、数据破坏可能产生相同索引/序号错误，校验器不会仅凭这两个字段猜测根因。`accepted_words` 为此前接受的字数，也就是首个坏字的零基位置；`expected_word` 和 `observed_word` 在索引/序号错误时记录对应字。结束/长度错误的 observed 字段不用于诊断。`complete_frames` 仅计算已按顺序验证完的帧。

结束时必须给出本次请求的帧数：如果只看连续序号，少掉最后一个完整帧无法与正常提前结束区分。调用者传入真实的采集目标，不能用已收到的帧数代替目标。此格式也无法识别恰好跨越整个 16 位序号空间、且总计数信息同时丢失的重放；本步不增加新的格式字段。

## 本次离线证据

第四小步已改为实际实例化 `daq_stream_top`，完成同样的 12 帧采集和 16 项 C 测试，并检查采集结束后的背压保持；最新证据见 [top_integration](../results/top_integration/summary.json)。下文保留第三小步的原始结果与失败修复记录。

`tb_capture_stream.sv` 实际运行现有数据源和深度 3 FIFO，在输出背压下接收完整的 12 帧 × 7 字，共 84 字、336 字节，经历 137 个仿真时钟周期。CSV 中保留每个输出握手的周期、TDATA、TKEEP 和 TLAST。Python 仅将实际 CSV 中的 TDATA 序列化为小端字节，不用模型替代原始数据。

测试结果位于 [frame_validator_repair](../results/frame_validator_repair/summary.json)：GCC 的严格警告检查通过，AddressSanitizer 和 UndefinedBehaviorSanitizer 启用，16/16 项测试通过且未报告内存/未定义行为错误。详情见 [故障矩阵](../results/frame_validator_repair/fault_matrix.csv) 和 [C 运行日志](../results/frame_validator_repair/c_test.log)。

矩阵包含原始 RTL 数据整批/分批接收、缺字、重复字、错误索引、缺帧、重复帧、序号跳变、尾部少字/少完整帧、非整字长度、端序错误、超额帧、空采集，以及锁存错误后明确重置恢复。序号回绕用额外构造的 28 字 C 测试数据覆盖 `65534 → 65535 → 0 → 1`，在矩阵里标记 `synthetic_C_fixture`；不冒充这次 12 帧 RTL 采集的数据。

第一次运行在生成 RTL 数据之后、C 编译之前发生 WSL 路径转换错误。失败证据保存在 [runner_failure.log](../results/frame_validator/runner_failure.log)。将 WSL 调用由 shell 路径改为 `--exec` 直接传参后，在 `build/validator_debug/` 隔离副本中验证成功；两处执行参数修复已应用到正式脚本。随后仅使汇总里的 WSL 发行版名称跟随命令行参数。没有改变 RTL 或放宽任何检查。

复现全部链路（从实验根目录执行；换一个结果目录可保留本次证据）：

```powershell
& 'E:\python.exe' .\scripts\run_frame_validator.py --output results/frame_validator_recheck
```

Windows 需要已有 Icarus 及 WSL Ubuntu-22.04/gcc；可用 `--wsl-distro` 指定其他已配置的发行版。Linux 可用已有 Python 3、Icarus 和 gcc 直接执行同一脚本。编译及运行命令分别保存在 `rtl_compile.log`、`rtl_simulation.log`、`c_compile.log`、`c_test.log`。

## 后续 DMA 缓冲区接入边界

校验器只读取 CPU 已拥有的普通内存，不负责配置 DMA、轮询硬件或执行 cache 操作。传入的是驱动确认完成的实际有效字节数，不是分配容量或请求长度。本次序列要求每个 AXI-Stream 字的 `TKEEP=f`，内存中每字 4 字节且为小端；普通 DMA payload 不携带 TLAST/TKEEP 的独立元数据，因此 C 校验通过不能单独证明实际 TLAST 时刻正确，仍须结合 RTL 检查、DMA 完成状态和包长。

当前 `FRAME_WORDS=7`，每帧 TLAST 对应 28 字节的包。未来最小 Simple S2MM 路径按一次接收一个包、分别确认完成后连续 feed；336 字节离线文件不是一次硬件 DMA 接收。PG021 依据和具体接入顺序见 [Vivado 入口说明](../vivado/README.md#simple-s2mm一帧怎样对应一次接收)。

Linux 接入时，由可靠驱动负责 DMA 映射、完成状态、所有权交接和必要的同步。对于重复使用的 streaming DMA 映射，CPU 读取前按 DMA API 使用 `dma_sync_*_for_cpu`；交还设备前按映射类型和方向完成 `dma_sync_*_for_device` 等要求。CPU 虚拟地址不是可以直接写入设备的 DMA 地址。用户态校验器不能替代这些操作。依据：[Linux DMA mapping guide](https://docs.kernel.org/core-api/dma-api-howto.html)。

Standalone 接入可参考本仓库保留的 [AMD Simple Poll 原例程](../vendor/embeddedsw-xilinx_v2025.1/XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c)：例程有传输前的缓存处理和接收检查前的 invalidate。实际接入仍需匹配 BSP、存储属性、cache line 对齐、缓冲区布局及 DMA 完成状态；本次没有测量或验证 ZCU104 cache 一致性。

超时与恢复属于调用层：先保存 DMA 状态、已经确认有效的长度和校验错误；在驱动确认传输停止、旧缓冲区不再被 DMA 写入后，再按既定流程回收缓冲区。重新采集需协调源/FIFO 的周期边界并显式调用 `fv_reset`。本模块不自动忽略异常、跳过坏字、猜测新序号或启动硬件重跑。
