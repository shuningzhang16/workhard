# GitHub 上的离线检查

[Offline experiments 工作流](https://github.com/shuningzhang16/workhard/actions/workflows/offline.yml) 调用与本机相同的 `scripts/check_offline.py`，按 P1/P2/P4 分成三个独立任务。运行环境为 Ubuntu 24.04、Python 3.13；P2 在临时运行环境安装 Icarus Verilog 与 GCC。它不生成 FPGA bitstream，不连接硬件，不发布软件包。

首次实际运行 [41804047532](https://github.com/shuningzhang16/workhard/actions/runs/41804047532) 的三个任务均成功，对应提交 `9ba952e`。GitHub API 返回的状态和 artifact 清单保存在 [验证记录](../verification/github-actions/41804047532.json)。后续结果以各次运行关联的提交为准，不能把前一次成功当成后来代码的证明。

实验目录、统一检查脚本或工作流发生改动时，推送到 main 和拉取请求会触发检查；也可以在 Actions 页面手动运行。纯根目录说明或图表更新不会触发这些任务。工作流没有添加分支合并要求。

每个任务保留退出码、完整测试日志；P2 另保留真实 RTL 轨迹、编译日志和 C 故障矩阵。失败时也执行结果上传，统一脚本会在控制台打印最后 30 行错误日志。运行页面下的 `offline-p1-*`、`offline-p2-*`、`offline-p4-*` artifacts 保存 14 天；长期阶段证据仍随各实验代码提交到 Git。

配置见 [.github/workflows/offline.yml](../.github/workflows/offline.yml)。工作流令牌使用只读仓库权限，官方 actions 使用版本标签，未新增提交校验摘要或自建发布门禁。路径触发与权限的语义依据 [GitHub 工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)，日志产物的保存方式依据 [GitHub artifacts 文档](https://docs.github.com/en/actions/tutorials/store-and-share-data)。

P2 的主机 C 检查包括帧校验器的 16 个用例和 Simple S2MM 接收/显式恢复的 13 个用例。后者先运行前者并复用其实际 RTL 捕获，因此统一入口不重复执行同一组帧校验测试。

P2 还安装 Yosys，执行 `scripts/check_synthesis.py`：通用综合后，用原有激励分别运行 RTL 和网表，逐项比较 84 个接收记录。相关脚本变更同样触发工作流；综合、网表仿真日志和版本信息包含在 `.runs/` artifact 中。本机的成功记录及首次依赖失败见 [综合验证记录](../verification/yosys-stream/README.md)。

新增的 AXI4-Lite wrapper 由统一入口运行 `run_axi_lite.py`，并在 Yosys 步骤以 `--control` 再次运行原 RTL/网表重放。比较包含 457 个 stream 周期和 161 个总线握手记录；TVALID=0 的无效载荷不参与比较，原始日志仍保留。[控制接口综合记录](../verification/yosys-control/README.md)

加入接收流程和综合步骤后的实际运行 [41806027084](https://github.com/shuningzhang16/workhard/actions/runs/41806027084) 全部成功；[API 记录](../verification/github-actions/41806027084.json) 包含各步骤状态及日志产物信息，对应提交 `39ee557`。

这组任务验证 Python 模型、Icarus RTL、通用网表和主机 C。SPICE 独立对照在 P1 阶段记录中单独保存；完整 Vivado、目标器件时序、PS BSP、DDR/cache 行为和实物测量仍不在当前工作流的验证范围。
