# 死区验证案例标签修正

2026-11-05 复核已完成的六个 ngspice 网表时发现两个标签不准确。首轮数值对照已通过，问题是标签的物理含义，不是求解失败或保护放宽。

| 原标签 | 初始原边电流 / A | 实际换流 | 修正标签 |
| --- | ---: | --- | --- |
| `sps_opposing_primary` | −0.8654625793861894 | 原边 A 上升/B 下降，初始方向有利 | `sps_favorable_primary` |
| `sps_incomplete_secondary` | −0.5960498941517469 | 副边 A 上升/B 下降，初始方向相反 | `sps_opposing_secondary` |

原始脚本、网表、数据和日志保存在本地忽略目录 `original/`。在 `work/` 的隔离副本只修改上述两个字符串；不更改电路、初态、求解器参数、比较容差或物理判据。

实际隔离验证命令（从 P4 实验目录执行；PYTHONPATH 指向该实验目录）：

```powershell
& 'E:\python.exe' -B -X utf8 .\diagnostics\deadtime_label_01\work\verify_deadtime_spice.py --source .\results_eps\comparisons.csv --output .\diagnostics\deadtime_label_01\validated
```

六个网表重新运行成功，每个实际日志退出码均为 0；最大节点差 1.189542 mV，最大电流差 6.571518 µA，与原结果一致。通过后将已验证脚本及输出复制回主实验位置。`before_summary.csv` 与 `after_summary.csv` 保留修正前后的实际汇总；原始全量证据与隔离副本留在本地，避免重复上传。

标签修正后的隔离运行实际命令保存在本地 `validated/run_metadata.json`。全量 24 组 Python 换流结果、原 33 项测试及本步新增换流测试均未因标签而变更；该次完整测试为 36 项通过。

随后按只读复核建议，修复运行器在 ngspice 退出码为 0 但未导出时可能复用旧文件的问题。修复前的脚本和六份有效结果保留在本地 `before_output_validation/`。新增 2 项普通单元测试，模拟无新导出和非有限/不完整轨迹；最终完整测试为 38 项通过，六个网表在主目录实际重跑成功，最新实际命令在 `results_deadtime_spice/run_metadata.json`。这是针对具体复跑风险的最小 I/O 修复，未发现原有效波形有误，也未改动模型或比较容差。
