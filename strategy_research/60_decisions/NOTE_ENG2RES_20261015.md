---
id: NOTE-ENG2RES-20261015
title: 工程侧 → 研究侧 问题确认单（五项；Q1 需用户决策；Q4/Q5 经独立核验修正）
status: 待研究侧确认（全部五项已独立核验；Q4 增加工程行动项，Q5 状态修正）
created: 2026-10-15
author: 工程侧（ENG，部署核验会话）；独立核验：VER（工程↔研究边界管道，2026-10-15 13:1x-13:4x）
related: [HO004, HO005, HO006, MTG004, RS015, RS018, RS019, RS020]
---

# 工程侧 → 研究侧 问题确认单

> 工程侧在部署核验与统一出口实施中发现以下需研究侧确认/决策的事项。
> 本版已由独立核验员逐项复核（读码/重算/远端只读核验），修正两处失实
> （Q4 TTL 未生效、Q5 未上线），证据以 文件:行 或 命令+输出 摘注。
> **Q1 需用户决策；Q2/Q5 需研究侧答复；Q3 研究侧执行+判读；Q4 升级为
> "工程行动项 + 研究侧确认观察口径"。**

## Q1（需用户决策）：引擎 EMA20 接刀检测器仍在武装——是否退役？

**证据链（核验 ✅，行号与部署机 md5 一致）**：
- `vnpy_patiming/signals/detectors.py:198` `EmaPullbackDetector`（EMA20_PULLBACK）：
  **无启用开关**（对比 `PullbackOrdinalDetector` :613 `enable_h1_l1`、
  `WmDetector` :694 `enable_w_m`，均有 cfg 门控且默认 False）——context ∈
  {trend_strong, trend_channel}（:208）+ EMA 触碰（:214）即武装；
- `runtime.py:239-243`：`signal_categories == "ALL"` 的指令白名单含 `ema_pullback`
  ——省略 signal_categories 的指令默认落 "ALL"（engine.py:321、:364 `_clean`）；
- `detectors.py:770-782` `DETECTOR_CLASSES` 注册表在位（EmaPullbackDetector=:774）；
- 部署一致性：106 上 `/opt/aiprj/vnpy_patiming/{runtime,engine,config}.py` 与
  `signals/detectors.py` 的 md5 与本地仓逐字节一致
  （d79992e4/636cb3d5/b230dd07/d7b89eea，`md5sum` 实测）。

**核验修正两处（不改变结论，改变表述与行动面）**：
1. 【原声明修正】`config.py:46` `REASON_DEFAULT_SIGNALS["TREND_FOLLOW"]` 确含
   `ema_pullback`，但该映射是**死配置**——全仓 grep 仅定义处一处引用
   （config.py:44-50），无任何消费方（MTG003 已定性"静态雏形"）。删除它是
   卫生动作，**不是**武装路径；真实武装路径是下面两条。
2. 【原声明修正】"LLM 渠道指令默认 ALL" 不精确——LLM 渠道两条路都武装：
   ① `services/HERMES_MCP_PROMPT.md:42-48` 默认表 **显式填**
   `TREND_FOLLOW -> ["ema_pullback","structure_pullback","h2_l2"]`
   （`hermes-skill/SKILL.md:41` 同含 ema_pullback）；② 省略 signal_categories
   时 `HERMES_MCP_PROMPT.md:97`"省略 = 全部启用" → engine.py:364 落 "ALL"。
   **即按文档口径，LLM 渠道不省略也带 ema_pullback。**

**生产在武装的直接实证（补充，比 ALL 更强）**：
- 106 线上 `services/selection_runner.py:395`（版本 716aa3d4，HO005 批）
  `_reason_signals` 回退返回 `["ema_pullback", "structure_pullback"]`——
  **今日 13:30 实际提交的选品指令即携带 ema_pullback**
  （journalctl -u selection-runner：`closed_at=...13:30:02 entries=1
  symbols=['CF0']` → `submitted=1`）。HO006 已把 staged runner 改为
  `["structure_pullback"]`（selection_runner.py:395、poolscan.py:160），随
  10-16 04:15 部署生效——**部署前生产每收线都在武装已否决形态**。

**该检测器的其它门控（核验 ✅，均为质量闸门非启用开关）**：
direction+趋势侧闸门（signals/__init__.py:91-102，trend_strong 只顺势）、
pivot 存在性（detectors.py:221-223）、止损距离 ≤max_stop_atr（:228-236）、
`passes_quality`（runtime.py:269-279 → signals/__init__.py:125-140：K 线幅度
0.5-3×ATR、止损 0.5-2×ATR、重叠度 ≤0.85）。`ema_slope()`（→
`EMA.slope()`，structures.py:58，需 history≥6）与 `pivots.last()` 依赖在
runtime 任务环内均有供给（runtime.py:223-235），无障碍。

**矛盾（不变）**：MTG004 已否决 EMA20_PULLBACK（基线 −0.202、12/12 年负、
深跌闸门救援失败终局：`MTG004_基线评审纪要.md:12-13,25,125`、
`assets/MTG004/ema20_rescue.md:28-29` 放行组 −0.1996≈原始 −0.202），
HO006-A1 已从选品武装列表退役——但**引擎通知路径（LLM 文档默认口径 +
部署前的选品回退列表）仍武装同一形态**。

**工程建议（维持，删去死配置项的紧迫性）**：①runtime ALL-allowlist 移除
`ema_pullback`；②`EmaPullbackDetector` 加启用开关默认 False（或从注册表
摘除）；③HERMES_MCP_PROMPT/SKILL 默认表同步去掉 ema_pullback；
④（卫生项）`REASON_DEFAULT_SIGNALS` 移除或标注 reserved（无消费方，零行为影响）。
需引擎重启窗口；**请研究侧确认语义（含 trend 分支后移的影响面）+ 用户批准。**

## Q2（需研究侧答复）：RS018 审计前提与 as-built 不符——B2/B3 暂缓是否成立？

**连续符号链核验 ✅（全链实证）**：
- 选品域：`poolscan.py:816-828` `_normalize_universe` 只保留 `endswith("0")`
  的主力连续代码（来源 futures_display_main_sina）；trend_pullback 固定
  products 全为连续符号（`pool_config.yaml:68-78`，RB0…IF0；106 远端
  `cat pool_config.yaml` 与本地一致）；
- 数据源：`vnpy_akshare/providers.py:67-68`——`endswith("0")` →
  `ak.futures_main_sina`（新浪主力连续，自动跟随换月）；
- 任务单构造：`services/selection_runner.py:398-435` `entry_to_instruction`
  `symbol = f"{base}{suffix}.{exchange}"`（RB0→RB0.SHFE）——**symbol 无合约
  月份**；instruction_id=`SEL-{closed_at stamp}-{symbol}-{direction}-{scanner}`；
- 池持久化键：`PoolStore`（poolscan.py:355-398）Redis HASH
  `quant:pool:entries`，field=`"{scanner}::{pool_id}"`，pool_id 含连续 symbol；
  全局 identity=`(scanner, symbol, exchange, direction)`（:328-331）；
- 生产实证：今日 13:30 journal `market_pullback 全市场扫描: universe=82`
  （样本全为 XX0.DCE/CZCE/SHFE/INE 连续代码）→ `symbols=['CF0']` → 提交。

**核验补充两点 as-built 事实（研究侧判读用）**：
1. HO005-B1 的 `PoolEntry.contract_code` 字段在位（poolscan.py:319）但**全仓
   无赋值点**——连续链上该字段恒为空串，"解析结果回写"实际未生效；
2. HO005-A3（旧合约预警抑制）未实现且裁剪未记录
   （`reviews_v2/phase_a_round9_review.md:176` MIN-2）；在连续符号+池每收线
   整体替换（`replace_scanner_entries`，poolscan.py:361-371）下结构性不适用
   ——池层暴露 ≤1 扫描节点（节点间隔最大 8h，`pool_config.yaml:34`）。

**B2/B3 暂缓的残余暴露场景（供研究侧判读，核验补充）**：
指令 key_levels/entry_ref 在收线时刻冻结；主力换月时 HO005-A1 重检切订阅 +
A2 发换月事件（poolscan.py:1306-1341、:1413-1434，payload 含
`"policy":"expire"` :1424），**但引擎不消费该字段自动失效旧指令**（B2 暫缓：
`engine.py:355-376 _clean` 键白名单丢弃，round9:44-48 裁定）——换月前提交的
指令以旧合约价格尺度存活至 TTL 到期（现状 12×60m=12h；TTL=8 落地后 8h；
`submit_entries` 不撤销上一代，selection_runner.py:483-537 仅按同 id 去重）。
**请研究侧确认**：该暴露（换月后 ≤TTL 窗口内的旧基差价位）是否可接受，
B2/B3 是否仍需要；若接受，建议把"换月事件→人工/自动撤销"的语义写入口径。

## Q3（需研究侧执行+判读）：HO004 验收启动 + v2 导出占比观察

- `context_tags_v2/` 六品种 CSV 已交付（**122,546 行复核无误**：RB/CU/AG/M/
  MA/TA 数据行合计 122,546，路径
  `vnpy_patiming/output/baseline/context_tags_v2/`）——请跑
  ho004_acceptance.py（B1/B2/B3）。**但先读下面的判读结论。**

- **观察项核验结论（独立重算）**：51.7% 属实——reversal 63,385 / 122,546 =
  **51.72%**（剔除 126 行空标签 = 51.78%），与
  `output/baseline/context_v2_acceptance.md:4-7` 自检一致，CHECK_NEEDED 属实。
  但**分母差异几乎不解释，根因是实现漂移，已定位**：

  | 假设 | 实测 | 结论 |
  |---|---|---|
  | 分母不同（GT 网格 STEP=4/horizon=20/i≥45/UNDEFINED 剔除） | 引擎标签投影到同一 GT v1.1 网格：9,876/19,191=**51.46%** vs 全 K 51.72% | **−0.3pp，不解释**（分品种 50.4%-52.6% 一致） |
  | EMA 差异 | 两侧均为 SMA 种子 EMA20（structures.py:47-52 vs context_v2_diagnostic.py:69-79） | **无差异（原声明修正）** |
  | ATR/复权差异 | 引擎 Wilder+拼接 vs 研究 TR 滚动均值+原始价（structures.py:31-35 vs diagnostic:57-66；_detect_and_splice） | ≈−0.5pp，次要 |
  | **R-C "回撤比例"(f_half) 分支实现不一致** | 同一 GT v1.1 网格 n=25,641：研究严格版+链掩码=**35.4%**（精确复现发表值 9,089/25,641，assets/RS015/context_v2_diagnostic.md:9,31；GT v2 口径 36.2%=10,793，rev2_retest_and_range_screen.md:28）；引擎宽松版+链掩码=**52.7%**（≈引擎导出 51.5-51.7%） | **主因 ≈+17pp** |

  漂移细节：研究参考实现（context_v2_diagnostic.py:154-159）某腿回撤比例
  **仅在该腿自身 ≥2.0×ATR 时计入**；引擎实现（baseline_backtest.py:189-192，
  已部署 md5=59a559fd）只要任一腿 ≥2.0×ATR，两腿回撤比例**无条件取或**。
  引擎版更宽松 → reversal 大量吞掉 trend 位（v2 导出 trend 合计仅 11.6%）。
  交叉验证：逐根复刻引擎管道与 CSV 100% 一致（RB 17,658/17,658）。

- **判读建议（写入验收前置）**：context_tags_v2 的 reversal 列 ≠ HO004 B1/B2
  预注册语义（对齐 rev_C 严格版，HO004 移交单明示"B1 验收 runner 按此对齐"）。
  **建议：工程侧先修 baseline_backtest.py:189-192 对齐参考实现并重导出 v2
  CSV，研究侧再跑 B1/B2**（或研究侧显式改判宽松语义并重预注册 25-45% 区间——
  不推荐，等同验收前改定义）。参考：宽松版现状对 GT v2 的列精确率 31.7%
  （基率 29.8%，LR≈1.06）名义擦线达标，但系漂移语义下的数字，不能替代验收。

  **【10-15 13:5x 工程侧处置：已修复并重导出】**baseline_backtest.py:189-192
  已对齐参考实现（f_half 按腿各自 ≥2×ATR 门控，本文件同批入库）；v2 CSV 已
  重导出（122,587 行）。**研究侧现可直接跑 B1/B2/B3 验收**——其中 B3 项工程
  侧先予定性：**v2 BREAKOUT 与 v1 锚逐位一致**（fires=3834、prec=0.317684
  两侧相同，breakout 分支未动，结构性保证兑现）；B3 判负系 ho004_acceptance
  门槛常数 `>= 0.318` 从舍入显示值 31.8% 标定所致——**v1 锚自身也过不了该门
  （0.317684 < 0.318）**，属门槛校准缺陷而非退化；请研究侧把门槛改为锚定
  比较（v2 ≥ v1 anchor 实测值）或加舍入容差后重判。

## Q4（核验后升级：工程行动项）：TTL 决议——**"已实施"不成立，TTL 仍=12**

【工程侧原声明有误】用户 2026-10-15 定案 `valid_bars` 12→8（TTL=选品周期×8）
**尚未生效**——现状线上=12，已排期的 HO006 部署（10-16 04:15）后**仍=12**：

- 已做对的两处（staged，随 HO006 部署）：poolscan.py:323 数据类默认 8 ✓；
  selection_runner.py:434 回退 `or 8` ✓（线上 runner 716aa3d4:434 仍 `or 12`）；
- **失效原因**：两条扫描器主路径**显式传参覆盖默认**——
  poolscan.py:602（trend_pullback）/ :1092（market_pullback）
  `valid_bars=max(1, int(self.cfg.get("timing_valid_bars", 12)))`，而生产
  `pool_config.yaml` **无 `timing_valid_bars` 键**（106 远端 cat 实证）→
  entry.valid_bars=12（真值）→ runner `or 8` 不触发。线上版本同样
  （648b 版 :284 `valid_bars: int = 12`、:563/:1052 同回退 12）；
- **生效所需（二选一，需工程侧行动）**：① 远端 pool_config.yaml `scan:` 节
  增 `timing_valid_bars: 8`（纯配置，随下次 runner 重启生效）；或
  ② poolscan.py:602/:1092 回退改 8 再部署；
- **【10-15 13:5x 工程侧处置：② 已落地】**poolscan.py:602/:1092 缺省已改 8
  （代码级），随 HO006 部署 10-16 04:15 重启 selection-runner 生效；Engine
  侧护栏核验 ✅：`validity_shorter_than_two_exec_bars` 在位
  （engine.py:393-395；1d 选品语义注释 :389-392；部署 md5=本地一致）；
- "12 残留"全清单（生产路径）：上两处扫描器回退 + 线上 runner:434 + 引擎
  指令缺省 `default_valid_bars=12`（config.py:54，语义不同：指令未填
  valid_bars 时的引擎缺省；HERMES 测试版默认 24）。
- **结构破坏即出池=长期方向暂缓**（依赖形态/信号准确量化——v1 reversal、
  ema_pullback 同源教训；Q3 的实现漂移再次佐证量化口径需验收前置），待量化
  能力成熟再立项。**观察期 KPI 口径请按 TTL 实际生效值执行**——在 ①/② 落地
  前 KPI 仍按 TTL=12 计算，请研究侧知悉并确认切换时点。

## Q5（状态修正）：入选跟踪 JSONL——已实现+已排期，**尚未上线**

【工程侧原声明有误】"已上线"不成立（截至 2026-10-15 13:4x）：
- 代码已就绪（staged，随 HO006 部署）：`poolscan.py:257-292` `_track_selection`
  append-only、50MB 轮转 `.jsonl.old`（:258）、异常不阻断投递（:292）；
  **11 字段与 HO006 §A2 逐一一致**（HO006:37-38）：ts/entry_id/symbol/scanner/
  direction/entry_ref/support/resistance/rr/exec_tf/ttl_expire（:276-287）；
- 远端只读实证：`ls /opt/aiprj/data/` → **目录不存在** → 文件不存在；线上
  poolscan（648b 版）grep 无 `_track_selection`（该批代码未含跟踪写入）；
- 生效时点：`deploy/ho006_deploy_20261016.sh`（:9 :53 `install -d
  /opt/aiprj/data`）2026-10-16 04:15 部署，**当日 10:16 首扫后**应存在
  （smoke: `ls` 存在 + journal 无 "入选跟踪写入失败"，:12-13）。
  RS019/RS020 观察期 KPI 数据源自此起才可用；回填脚本
  （fwd_{1,3,5,20}d/outcome）按 HO006 §A2 登记为后续交付。

---

## 附：核验方法与边界（VER，2026-10-15）

- 本地：逐行读码 + 全仓 grep 消费方分析；Python 独立重算（CSV 反占比、
  GT v1.1 网格 n=25,641 投影、2×2 语义分解、引擎管道逐根复刻比对）；
  本地关键文件 md5 与部署/暂存清单比对（detectors d7b89eea=线上、
  baseline_backtest 59a559fd=线上、engine 636cb3d5=线上、config b230dd07=线上、
  poolscan dd6d7939=HO006 暂存、selection_runner 52618f1b=HO006 暂存）。
- 远端（ssh tony@192.168.50.106，只读 ls/md5sum/cat/grep/journalctl）：部署
  md5 六文件一致；pool_config.yaml 无 timing_valid_bars；/opt/aiprj/data 不
  存在；线上 runner `_reason_signals` 回退含 ema_pullback；今日 13:30 扫描
  submitted=1（CF0 连续符号）。
- 边界：未读生产 patiming.db 内容（只读纪律，sqlite 不在许可命令内）——
  "LLM 存量指令中 ALL/显式类别的分布"未逐一枚举，Q1 结论基于代码路径 +
  文档口径 + 选品通道实证；Hermes 助手实际生效的系统提示词在网关应用配置内，
  以仓内 HERMES_MCP_PROMPT.md/SKILL.md 为文档口径证据。
