# GitHub 上的离线检查

[Offline experiments 工作流](https://github.com/shuningzhang16/workhard/actions/workflows/offline.yml) 调用与本机相同的 `scripts/check_offline.py`，按 P1/P2/P4 分成三个独立任务。运行环境为 Ubuntu 24.04、Python 3.13；P2 在临时运行环境安装 Icarus Verilog 与 GCC。它不生成 FPGA bitstream，不连接硬件，不发布软件包。

首次实际运行 [41804047532](https://github.com/shuningzhang16/workhard/actions/runs/41804047532) 的三个任务均成功，对应提交 `9ba952e`。GitHub API 返回的状态和 artifact 清单保存在 [验证记录](../verification/github-actions/41804047532.json)。后续结果以各次运行关联的提交为准，不能把前一次成功当成后来代码的证明。

完整控制功能及主机 C 整合后的运行 [41808673908](https://github.com/shuningzhang16/workhard/actions/runs/41808673908) 三项均成功，对应提交 `2848576`。这次 Ubuntu 24.04 实际执行了 P1 的 C 对照、P2 的 AXI-Lite 与两项 Yosys 重放、P4 的 33 项测试；[API 状态与日志产物记录](../verification/github-actions/41808673908.json) 随仓库保存。

2026-11-05 加入 P1 延迟/量化及 P2 队列后，运行 [42049358300](https://github.com/shuningzhang16/workhard/actions/runs/42049358300) 的三个任务均成功，对应 `81660b3`；此时 P4 是已提交的局部死区版本。[API、任务及产物记录](../verification/github-actions/42049358300.json) 与 [本机 P1/P2 定向整合日志](../verification/2026-11-05-integration/) 一并保存。

实验目录、统一检查脚本或工作流发生改动时，推送到 main 和拉取请求会触发检查；也可以在 Actions 页面手动运行。纯根目录说明或图表更新不会触发这些任务。工作流没有添加分支合并要求。

每个任务保留退出码、完整测试日志；P2 另保留真实 RTL 轨迹、编译日志和 C 故障矩阵。失败时也执行结果上传，统一脚本会在控制台打印最后 30 行错误日志。运行页面下的 `offline-p1-*`、`offline-p2-*`、`offline-p4-*` artifacts 保存 14 天；长期阶段证据仍随各实验代码提交到 Git。

配置见 [.github/workflows/offline.yml](../.github/workflows/offline.yml)。工作流令牌使用只读仓库权限，官方 actions 使用版本标签，未新增提交校验摘要或自建发布门禁。路径触发与权限的语义依据 [GitHub 工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)，日志产物的保存方式依据 [GitHub artifacts 文档](https://docs.github.com/en/actions/tutorials/store-and-share-data)。

P2 的主机 C 检查包括帧校验器 16 项、Simple S2MM 接收/显式恢复 13 项、正常启停会话 9 项，以及有界队列 13 项与 9 组主机测量。统一入口调用 `run_daq_queue.py`，它依次包含会话、AXI-Lite、帧校验和接收流程，避免重复运行这些检查。测量中的吞吐和延迟只属于主机回调工作负载，不能推断硬件性能。

P1 同时安装 GCC，通过 `host_c/run_validation.py` 编译独立 C 控制模块，执行 ASan/UBSan、边界检查及四份 PWM 采样数据的逐拍对照；Python 自动发现测试目前为 13 项，包含延迟与量化。P1 的 `.runs/` 中保留 C 编译命令、输出和全部比较结果，一并上传 artifact。DAB 的 Python 测试自动发现已有 SPS/EPS、保护、功率 PI、死区等测试，具体数量以对应提交的日志为准。

P2 还安装 Yosys，执行 `scripts/check_synthesis.py`：通用综合后，用原有激励分别运行 RTL 和网表，逐项比较 84 个接收记录。相关脚本变更同样触发工作流；综合、网表仿真日志和版本信息包含在 `.runs/` artifact 中。本机的成功记录及首次依赖失败见 [综合验证记录](../verification/yosys-stream/README.md)。

AXI4-Lite wrapper 通过会话入口运行 `run_axi_lite.py`，并在 Yosys 步骤以 `--control` 再次运行原 RTL/网表重放。最初比较包含 457 个 stream 周期和 161 个总线握手记录；增加独立采集复位后，最新本机重放包含 546 个周期和 188 个总线记录，均一致。TVALID=0 的无效载荷不参与比较，原始日志仍保留。[早期记录](../verification/yosys-control/README.md)、[采集复位后的实际结果](../verification/yosys-control/stream-reset/summary.json)

加入接收流程和综合步骤后的实际运行 [41806027084](https://github.com/shuningzhang16/workhard/actions/runs/41806027084) 全部成功；[API 记录](../verification/github-actions/41806027084.json) 包含各步骤状态及日志产物信息，对应提交 `39ee557`。

这组任务验证 Python 模型、Icarus RTL、通用网表和主机 C。P1/P4 的实际 ngspice 对照及 P1 的真实 C2000 目标编译在各阶段单独保存，不在 CI 中重复安装相应工具。完整 Vivado、目标器件时序、PS BSP、MATLAB、DDR/cache 行为和实物测量仍不在当前工作流的验证范围。
