# RD264 原始资料来源记录

核验日期：2026-11-04。以下为自主整理的来源索引及简要事实记录，未镜像原厂资料。

## 已核验来源

| 官方来源 | 版本或定位 | 本次核验范围 |
| --- | --- | --- |
| [RD264 设计页面](https://toshiba.semicon-storage.com/us/semiconductor/design-development/referencedesign/detail.RD264.html) | 页面所列资料日期为 2026 年 5 月 | 设计编号、规格、公开下载分类与器件列表 |
| [RD264-RGUIDE-01，Reference Guide](https://toshiba.semicon-storage.com/info/docget.jsp?did=169554) | Rev.1，2026-05-29，19 页 | 封面、目录、第 4 页规格、第 19 页 Terms of Use |
| [RD264-DGUIDE-01，Design Guide](https://toshiba.semicon-storage.com/info/docget.jsp?did=169558) | Rev.1，2026-05-29，13 页 | 封面、目录、第 3 页拓扑说明、第 13 页 Terms of Use |
| [网站 Terms and Conditions of Use](https://toshiba.semicon-storage.com/us/terms.html) | Single Copy License / Ownership Of Materials | 下载、版权及分发限制 |

## 编号、规格与公开内容

RD264 是 10 kW 双向 DAB 参考设计。参考指南第 4 页给出的两侧工作电压为 750 V 与 400 V，开关频率为 50 kHz；这些是原厂设计规格，不是后续教学模型参数，也不是本项目测量值。该表没有给出可直接据此采用的完整电压工作范围。

设计页面列出的开关器件为高压侧 TW060N120C、低压侧 TW048N65C，另列出 TLP5214A 驱动器及 TLP7920 隔离放大器。[来源：设计页面](https://toshiba.semicon-storage.com/us/semiconductor/design-development/referencedesign/detail.RD264.html)

该页面的 Design Documents 列出 8 项：参考指南、设计指南，以及主板和控制板各自的原理图、BOM、PCB 分层图。Design Data 列出 12 项硬件 EDA/CAM 数据：5 种原理图格式、5 种 PCB 格式，以及 Gerber 和 ODB++ 制造数据。这些硬件设计文件不能据此称为可运行的控制源码或 DAB 仿真模型。

## 模型及源码检索结论

本次检查上述公开目录，并补充检索 Toshiba 官方域名下 `RD264 Simulink`、`RD264 software`、`RD264 model`；未找到明确的原厂仿真模型或固件源码下载项。这个结论仅描述本次公开入口的检索结果，不证明厂商内部或其他渠道不存在模型或源码。

未下载、解压或逐文件审计 CAD 包，未验证其 EDA 工具兼容性，也未取得完整设计包。浏览工具不能直接展示 ZIP 内容；页面存在 CAD 下载入口不构成源码已取得的证据。

## 许可与本次收录范围

两份指南均标有 Toshiba Electronic Devices & Storage Corporation 的 2026 年版权。指南末页 Terms of Use 的 Section 1.2 限制出售、出租及其他转让；网站 Single Copy License 与 Ownership Of Materials 对复制、公开传播及分发另有约束。[参考指南第 19 页](https://toshiba.semicon-storage.com/info/docget.jsp?did=169554) · [设计指南第 13 页](https://toshiba.semicon-storage.com/info/docget.jsp?did=169558) · [网站条款](https://toshiba.semicon-storage.com/us/terms.html)

本次未发现可据以将上述资料公开上传到 GitHub 的授权，亦未核验任何 CAD 包内可能附带的独立许可。因此当前只收录来源链接和简要核验说明，不收录或重新许可厂商文件。官网关于可编辑 EDA 数据的介绍不能单独作为公开再分发许可。后续如取得具体文件及明确授权，应保留该文件实际附带的版权和许可。

目前可以准确描述为“参考 Toshiba RD264 公开资料开展 DAB 学习准备”，不能描述为“已取得原厂源码”“完整复现 RD264”或“已验证双向转换性能”。
