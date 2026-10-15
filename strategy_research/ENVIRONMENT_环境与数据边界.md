---
id: ENVIRONMENT
title: 环境与数据边界清单（可行性筛查的权威依据）
status: living
created: 2026-10-12
updated: 2026-10-14
# 标注规则：✅=本对话内已核实；❓=待工程侧确认；推断项必须带 ❓
---

# 环境与数据边界清单

> 用途：RS003 §2.0.1 可行性筛查的权威依据；对外需求/依赖的登记表。
> 本清单由研究团队维护，**核实状态如实标注**，不把推断写成事实。

## 1. 行情数据（✅ 已核实，TRADEPLAY_DATA = D:/AIprj/tradereplay/data）
- **周期目录**：1m / 5m / 15m / 30m / 60m / day
- **交易所**：CFFEX / CZCE / DCE / GFEX / INE / SHFE（六大所齐全）
- **品种覆盖**：60m 下 6 主连已验证（RB/CU/AG/M/MA/TA）；1m SHFE 下品种众多（AD/AG/AL/AO…），**全品种清单 ❓ 待盘点**
- **5m/日线全历史（✅ 2026-10-14 实测，重大更正）**：**5m 为 2009-03 起 17 年全历史**（RB 实测 2009-03-27→2026-10-14 实时前向；六大所 **97 品种目录**：SHFE 20/CZCE 33/DCE 26/GFEX 5/INE 5/CFFEX 8）——**并非 1m 那样的 1 个月前向**；**day 91 个品种 CSV**（平铺 `{EXCH}.{SYM}.csv`，SHFE.RB 2009-03-30→2026-10-13）。→ **Hermes 思路（5m 横盘/回踩/积分）的合并回测本地完全可行**（RS020）
- **1m 品种级覆盖（✅ 2026-10-14 核实）**：按品种单 CSV（如 1m/SHFE/RB/RB.csv，列同 60m，symbol=主连 RB0），2026-09-07 起前向采集；**生产池 10 主连全部有 1m 品种目录**（RB/AL/CU/M/Y/P/TA/MA/SR/IF）
- **60m 覆盖缺口（✅ 2026-10-14 核实）**：生产选品池 10 主连中 **AL0/Y0/P0/SR0/IF0 无本地 60m 历史**（选品回放仅可做 5 品种子集，RS017 §5.2.2）
- **直拼警示（✅ 2026-10-14 实测）**：5m 与 60m 同为**未复权直拼**主连（symbol RB0909→RB0，换月跳变在序列中）——收益类研究必须先做后复权（DEC006/`_detect_and_splice` 同款）
- **CSV 列**：datetime, open, high, low, close, volume, amount, position, symbol（分合约，主连拼接由工程管道负责——HO001 依赖 `_detect_and_splice`）
- **额外资产（✅ 意外发现）**：`binance_cache` / `hyperliquid_cache` 存在**加密货币 USDT 永续 K 线**（1m/15m/1d 等多周期）——跨市场依赖部分可得（详见 §3）

## 2. 执行环境（✅ 已知；生产仓/部署拓扑 2026-10-14 补录）
- **环境分层（✅ 用户确认 + SSH 核实）**：本机 Windows = **开发测试环境**；**106 生产机（192.168.50.106，SSH 别名 webserver106，用户 tony/密钥）= 生产运行**。两机均有 .vntrader：本机含 2 个 LinuxSignalScanner 开发/测试实例（非生产）
- 框架：vnpy + 用户自研 `vnpy_patiming`（9 detector；selection 60m + exec 1m 双层）
- 研究代码：`strategy_research/code`（RESEARCH ONLY，与工程零依赖）
- 因子库：`vnpy/alpha`（polars AlphaDataset、ts_* 算子、Alpha101/158、alphalens——RS002 评估：限纯时序场景可用）
- **生产仓（✅ 2026-10-14 只读侦察补录）**：`D:/AIprj/quant-repo`（Linux 生产机部署；本机同名目录只读侦察用）——
  - `strategies/`：LinuxSignalScanner（只预警形态探头，CTA 实例 rb2701/M2701 15m）、
    MarketPullback/TrendPullback（组合选品，universe=10 主连，selection_timeframe 60m/1d）、
    RegimeSwitch（择时 CTA，真实下单，settings=regime_switch_settings.json：bar_window=1/fixed_size=2/risk_capital=20万）
  - `poolscan.py`+`pool_config.yaml`：监控池引擎（扫描节点 10:16/11:31/15:05/23:05/01:05；scanners=[trend_pullback, market_pullback]）
  - `deploy/`：systemd 服务（vnpy-core/selection-runner/patiming-engine/quant-afterhours/shadow-watchdog 等）；
    **106 在运核实（2026-10-14）**：running=patiming-engine / patiming-webhook / selection-runner /
    quant-shadow（Phase A 影子）/ quant-webhook / quant-mcp / quant-pattern / hermes-gateway /
    quant-shadow-watchdog.timer / vnpy-sync.timer（会后 AKShare 同步）；**未运行=vnpy-core（CTA 面，
    cta_strategy_setting 为空）与 quant-afterhours**
  - 框架契约：选品↔择时接力（`TEMPLATE_选品择时接力框架.md` v1.0 固化）；择时=PA 择时引擎一个策略监控全部选品池，只预警
- **本机 `~/.vntrader`（✅ 已核实）**：仅 2 个 LinuxSignalScanner 实例（rb2701/M2701）；database.db 无成交记录（仅 105 根 bar）——**实盘绩效数据在 Linux 生产机**

## 3. 数据边界（不可得/待确认项）
| 类别 | 状态 | 说明 |
|------|------|------|
| tick/逐笔/订单簿 | ❓ 待工程确认 | 数据目录未见对应结构 |
| 基本面/库存/仓单/COT | ⛔ 未见 | 不为基础面依赖策略立项 |
| 期权链 | ⛔ 未见 | 同上 |
| 传统外盘（LME/COMEX 等） | ⚠️ **更正（2026-10-14）**：**Linux 生产机有外盘采集**——Hermes gap 链路（gap_snapshot/evening_gap_snapshot）每日抓 **COMEX 金银/WTI/标普/美元指数**（用于内盘跳空推算，`/home/tony/tradereplay/data/`），本机 tradereplay 未见；外盘联动研究素材在 Linux 机，跨市场策略落地仍需外盘行情接入评估 |
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
| R7 | **Linux 生产机绩效数据导出**（MTG006 决议 C 观察期 KPI 数据基线） | 工程侧/用户 | **待执行**：RegimeSwitch 成交+日权益+实例参数（BTE 方案≈0.5 人日：CTP 结算单×journalctl/策略日志对账，trades/daily/params 三张 CSV）；选品池历史快照或通知存档（选品跟踪回填）；导出前 RegimeSwitch 观察 KPI 无基线 |
| R8 | **D11 与磁盘事实差异确认 + 数据修复**（DEC006） | 工程侧 | **待确认（2026-10-14 实测）**：tradereplay 60m CSV 为**未复权直拼**（换月边界跳变实测 TA −24%/M −15%，487 处边界），与 requirements D11"比率拼接后"不符；MA 品种存在坏 bar（复权护栏跳过 34 处）。需工程确认：比率拼接版是否存在/是否由管道加载时生成（`_detect_and_splice`）；建议管道统一产出后复权 CSV 落盘 |
| R9 | **主力换月接力处理实现**（HO005，阶段 0+1） | 工程侧 | **已发工程（2026-10-14，用户批准）**：poolscan 粘性修复（resolved 每轮重检主力）+【主力换月】预警+旧合约预警抑制+schema v1.1（contract_code/rollover_policy=expire 默认/一致性检查 job）；择时引擎零改动；验收=单测+集成+下次真实换月生产观察（研究侧复核） |
| R10 | **选品选品 `market_min_rr` 上调至 ≥1.6**（用户 2026-10-15 确认） | 工程侧 | 修改 `pool_config.yaml` `market_min_rr: 1.0` → `1.6`；依据：区间中段入场最危险，正确入场应在边缘 1/3 以内（RR≥1.6~1.8）；同时武装列表修正按 HO006 执行 |

## 维护规则
- 每次 ❓ 项被工程侧答复后更新为 ✅/⛔ 并注明日期
- 新增依赖需求先进 §6 登记再外发
