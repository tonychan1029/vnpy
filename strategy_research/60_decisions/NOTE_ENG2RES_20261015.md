---
id: NOTE-ENG2RES-20261015
title: 工程侧 → 研究侧 问题确认单（五项；Q1 需用户决策）
status: 待研究侧确认（工程侧已附证据与建议）
created: 2026-10-15
author: 工程侧（ENG，部署核验会话）
related: [HO004, HO005, HO006, MTG004, RS018, RS019, RS020]
---

# 工程侧 → 研究侧 问题确认单

> 工程侧在部署核验与统一出口实施中发现以下需研究侧确认/决策的事项。
> Q1 涉及生产通知行为，需用户决策；Q2/Q5 需研究侧答复；Q3/Q4 为知会。

## Q1（需用户决策）：引擎 EMA20 接刀检测器仍在武装——是否退役？

**证据链（工程侧已核实）**：
- `vnpy_patiming/signals/detectors.py:198` `EmaPullbackDetector`（EMA20_PULLBACK）：
  **无启用开关**（对比 WmDetector 有 `enable_w_m` 门控）——context ∈
  {trend_strong, trend_channel} + EMA 触碰即武装；
- `runtime.py:239-243`：`signal_categories == "ALL"` 的指令白名单含 `ema_pullback`
  ——LLM 渠道指令默认 ALL → 该检测器会武装并推送通知；
- `config.py:46`：`REASON_DEFAULT_SIGNALS["TREND_FOLLOW"]` 默认含 `ema_pullback`；
- `detectors.py:774`：在检测器注册表中。

**矛盾**：MTG004 已否决 EMA20_PULLBACK（基线 −0.202、12/12 年负、深跌闸门
救援失败终局），HO006-A1 已从选品武装列表退役之——但**引擎通知路径仍在武装
同一形态**。用户会继续收到已否决形态的接刀预警。

**工程建议**：三处收敛——①runtime ALL-allowlist 移除 `ema_pullback`；
②`REASON_DEFAULT_SIGNALS["TREND_FOLLOW"]` 移除；③`EmaPullbackDetector`
加启用开关默认 False（或直接从注册表摘除）。需引擎重启窗口；HERMES 文档
默认口径同步。**请研究侧确认语义（含 trend 分支后移的影响面）+ 用户批准。**

## Q2（需研究侧答复）：RS018 审计前提与 as-built 不符——B2/B3 暂缓是否成立？

工程侧核实：生产任务单/数据全链为**连续符号**（rb0.SHFE，akshare 主力连续
自动跟随换月）；RS018 P2/P3 审计前提"任务单 symbol=具体合约"与 as-built
不符。HO005 已上线 A1（monitor 类粘性修复）/B1（contract_code）/换月事件；
**B2（rollover_policy 入 hash）/B3（一致性检查 REVOKE）暂缓**。
另 A3"旧合约预警抑制"在连续符号现实下判定不适用（池每收线整体替换，
暴露 ≤1 收线节点，自然有界）。
**请研究侧确认**：连续符号现实下 B2/B3 是否仍需要（若需要，请给出
"旧合约价格尺度"风险在连续符号链上的具体暴露场景）。

## Q3（需研究侧执行+判读）：HO004 验收启动 + v2 导出占比观察

- `context_tags_v2/` 六品种 CSV 已交付（122,546 行，路径已就绪）——
  请跑 ho004_acceptance.py（B1/B2/B3）。
- **观察一项**：工程侧全 K 导出自检 reversal 占比 **51.7%**（全 K 分母），
  高于研究侧网格口径 36.2%——分母不同（GT 抽样网格 vs 全 K）+ EMA/ATR
  实现差异；请判读是否存在定义漂移（影响 B1/B2 解读）。

## Q4（知会）：TTL 决议

用户 2026-10-15 定案：`valid_bars` 12→8（TTL=选品周期×8：60m→8h、
1d→8d），随 HO006 同批 10-16 04:15 部署。**结构破坏即出池=长期方向暂缓**
（依赖形态/信号准确量化——v1 reversal、ema_pullback 同源教训），待量化
能力成熟再立项。观察期 KPI 口径请按 TTL=8 对应周期。

## Q5（知会）：入选跟踪 JSONL 已上线

`/opt/aiprj/data/selection_tracking.jsonl`（HO006-A2；append-only、50MB
轮转、字段 ts/entry_id/symbol/scanner/direction/entry_ref/support/
resistance/rr/exec_tf/ttl_expire）——RS019/RS020 观察期 KPI 数据源就绪。
回填脚本（fwd_{1,3,5,20}d/outcome）按 HO006 §A2 登记为后续交付。
