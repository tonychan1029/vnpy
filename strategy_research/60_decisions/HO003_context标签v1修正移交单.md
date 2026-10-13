---
id: HO003
title: context_tag v1 修正与基线数据补充移交单
status: final（用户批准 2026-10-13："同意MTG004的全部决议——结果记录在案，未来可能需要重新验证"）
created: 2026-10-13
author: 研究团队（RES+QA 联署）
related: [RS012, RS013, MTG004纪要, ENVIRONMENT-R2, HO001, DEC003]
---

# HO003：context_tag v1 修正 + by_year 补导出

> 背景：HO001 基线交付的判定侧 context v0 经研究侧实测（RS012 §5 混淆矩阵
> n=19,167 + RS013 三重 regime 实验），暴露三类缺陷。MTG004 议程增补议题 d)
> 转为本移交单。**用户已批准（2026-10-13），附重验证条款（见纪要 §10）。**

## A. context_tag v1 修正（三项）

### A1. RANGE 条件放宽
- 现状：v0 条件（|close−EMA20| ≤ 0.25×ATR 且 40 根区间宽 ≤ 4×ATR）全程仅
  **0.9%** 时间触发（GT RANGE 占比 ≈17.5%）；判定侧 RANGE top-pred 精确率
  **39.8% < 40%** 预注册线 → 门控存疑（RS012 §5）
- 修正方向（建议，工程侧可调参实现）：放宽区间宽上限至 6×ATR、
  |close−EMA20| 放宽至 0.5×ATR（或直接以「40 根区间宽/ATR」分位数定义）
- **验收**：重跑 RS012 混淆矩阵（runner 就绪），RANGE top-pred 精确率 ≥40%，
  且 RANGE 标签触发占比 ≥8%
- **⚠️ 追加验收（2026-10-13，研究侧 RER 扩样分析 assets/MTG004/rer_expand.md）**：
  放宽后的 RANGE 会稀释 RANGE_EDGE_REVERSAL（裸形态 3.3 万笔扣费后转负，
  边际在「严格 range 环境 × 形态」交集）。要求 v1 采用**两层 range 定义**：
  宽口径 range（阶段判定用）+ 严格子态 strict_range（保留 v0 条件，供 RER 类
  边缘反转作闸门）。追加验收：RER 形态在 strict_range 下样本量与均收益
  不得显著差于 v0 口径（基准：269 多/+0.094%、227 空/−0.173%）

### A2. reversal 重定义
- 现状：引擎 reversal 列精确率 **15.7%**（939/1,908 级别的错配）
- 修正方向：reversal 需同时要求「斜率与 (close−EMA20) 异号」**且**
  「20 根前瞻不可知→改用已实现结构证据：如最近 5 根内出现 ≥1×ATR 的反向
  位移」，避免把所有斜率拐点都标成 reversal
- **验收**：reversal 列精确率 ≥30%

### A3. breakout 标签加迟滞/最小持续期
- 现状：**58% 的 breakout 标签只存活 1 根**（RS013 regime_exit.md）——
  标签闪烁使 regime 类研究在生产端不可实现；GT 版 +0.36 的突破段延续溢价
  被证实存在但两次入场机制均无法捕获（regime_retest.md）
- 修正方向：进入迟滞（连续 2 根 breakout 才置位）+ 退出迟滞（连续 2 根
  非 breakout 才复位）——与 S-004 armed 迟滞同构
- **验收**：breakout 标签中位持续期 ≥5 根；重跑 regime_retest.py，
  B_regime（确认后入场）不再差于 A_event

## B. by_year 补导出（低优先级）
- 现状：summary_by_year.csv 仅含 cost_tier=p0
- 需求：增加 p1/p2 档行（同 schema）；研究侧已用逐笔数据自行重建 p1
  （assets/MTG004/by_year_p1.md），此项仅为数据完整性

## 验收方式（统一）
- 修正完成后重跑研究侧两个脚本（免改造）：
  `rs012_confusion.py`（新 tags 经 tag_adapter 转换）与 `regime_retest.py`
- 两脚本输出即验收报告，无需工程侧另写

## 用户批准栏
- [ ] 批准 A1/A2/A3 + B 全部
- [ ] 部分批准（注明项号）
- [ ] 不批准（注明理由）
