---
id: ENVIRONMENT
title: 环境与数据边界清单（可行性筛查的权威依据）
status: living
created: 2026-10-12
updated: 2026-10-12
# 标注规则：✅=本对话内已核实；❓=待工程侧确认；推断项必须带 ❓
---

# 环境与数据边界清单

> 用途：RS003 §2.0.1 可行性筛查的权威依据；对外需求/依赖的登记表。
> 本清单由研究团队维护，**核实状态如实标注**，不把推断写成事实。

## 1. 行情数据（✅ 已核实，TRADEPLAY_DATA = D:/AIprj/tradereplay/data）
- **周期目录**：1m / 5m / 15m / 30m / 60m / day
- **交易所**：CFFEX / CZCE / DCE / GFEX / INE / SHFE（六大所齐全）
- **品种覆盖**：60m 下 6 主连已验证（RB/CU/AG/M/MA/TA）；1m SHFE 下品种众多（AD/AG/AL/AO…），**全品种清单 ❓ 待盘点**
- **CSV 列**：datetime, open, high, low, close, volume, amount, position, symbol（分合约，主连拼接由工程管道负责——HO001 依赖 `_detect_and_splice`）
- **额外资产（✅ 意外发现）**：`binance_cache` / `hyperliquid_cache` 存在**加密货币 USDT 永续 K 线**（1m/15m/1d 等多周期）——跨市场依赖部分可得（详见 §3）

## 2. 执行环境（✅ 已知）
- 框架：vnpy + 用户自研 `vnpy_patiming`（9 detector；selection 60m + exec 1m 双层）
- 研究代码：`strategy_research/code`（RESEARCH ONLY，与工程零依赖）
- 因子库：`vnpy/alpha`（polars AlphaDataset、ts_* 算子、Alpha101/158、alphalens——RS002 评估：限纯时序场景可用）

## 3. 数据边界（不可得/待确认项）
| 类别 | 状态 | 说明 |
|------|------|------|
| tick/逐笔/订单簿 | ❓ 待工程确认 | 数据目录未见对应结构 |
| 基本面/库存/仓单/COT | ⛔ 未见 | 不为基础面依赖策略立项 |
| 期权链 | ⛔ 未见 | 同上 |
| 传统外盘（LME/COMEX 等） | ⛔ 未见 | 外盘联动策略不可直接落地 |
| **加密行情** | ✅ 有缓存 | 跨市场联动研究可用（Binance/Hyperliquid USDT 永续）——注意：**与国内期货联动落地需外盘行情，仍不可行**，仅作研究素材 |
| 付费数据/私有研报 | ⛔ 无 | 研报正文需人工提供 |

## 4. 外部访问限制（✅ 本对话内已实测）
- TradingView 全域名：DNS 解析拦截（2026-10-12 复测仍拦）
- 聚宽帖子：JS 渲染，抓取只得到加载占位
- 研报 PDF：content-type 不支持 + 付费墙
- **结论**：外部源依赖工程侧访问解决（HO002 §5，已批准）

## 5. 算力/延迟约束（✅ 用户声明）
- 硬件受限——**HFT/低延迟策略不落地**；回测批量计算可接受（RS012 全样本 6 品种分钟级跑通）

## 6. 需求与依赖登记表（对外，living）
| # | 需求 | 依赖方 | 状态 |
|---|------|--------|------|
| R1 | 基线回测数据（HO001） | 工程侧 | **✅ 已交付**（2026-10-12 23:49，vnpy_patiming/output/baseline/）；findings：by_year 仅 p0 档（p1/p2 分年待补） |
| R2 | context_tag 序列导出（RS012 B 项） | 工程侧 | **✅ 已交付**（v0）；对接契约与 runner 见 assets/RS012/incoming/README。**v1 修正请求（2026-10-13，MTG004 后升级为三项，待批准）**：① RANGE 条件放宽（现仅 0.9% 时间触发、判定准确率不达标）；② reversal 列修正（精确率 15.7%）；③ breakout 标签加迟滞/最小持续期（58% 单根即离，闪烁使 regime 类研究在生产端不可实现——RS013 regime_exit.md 三重证据） |
| R3 | H1/W detector 实现（HO002-C） | 工程侧 | **✅ 已实现待独立评审**（PullbackOrdinalDetector + WmDetector，默认关闭，16 单测过——QUANT_HANDOFF 2026-10-12） |
| R4 | TradingView/聚宽/PDF 访问解决（HO002-D） | 工程侧 | **✅ 部分解决**（代理通道可读 TradingView ✅；聚宽需无头浏览器；付费 PDF 待人工） |
| R5 | 1m 全品种清单与数据边界确认（tick 有无） | 工程侧 | **研究侧已实测（2026-10-13）**：① tick 数据不存在（data 顶层仅 15m/1m/30m/5m/60m/day）；② 1m 为全市场 91 品种（含金融期货），但仅约 1 个月历史（RB: 2026-09-07 起，7,960 根）——实时前向采集非回补。**结论**：P2 分层变量来自品种规格（tick/价格比，RS011 附录 A 已有），不需要 tick 数据即可跑基线信号分层检验；1m 前向积累对未来 1m 级微观研究有价值，建议保持采集 |
| R6 | 数据采购类需求 | 用户单独批准 | 无（原则：不为单个候选采购） |

## 维护规则
- 每次 ❓ 项被工程侧答复后更新为 ✅/⛔ 并注明日期
- 新增依赖需求先进 §6 登记再外发
