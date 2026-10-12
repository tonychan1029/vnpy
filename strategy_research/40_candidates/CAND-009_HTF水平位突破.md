# CAND-009 HTF Level Breakout（vanchesz）

- **id**: CAND-009
- **name**: HTF Level Breakout（高周期水平位突破+首次触碰确认）
- **source**: https://www.tradingview.com/script/PdJvHIfQ-HTF-Level-Breakout/ （2026-10-12 采集，代理通道）
- **family**: 突破/结构确认（H1/L1 同构族）
- **status**: collected
- **impl_scope**: 日内~短期均可（HTF 可选 1H/4D/日/周）——按落地窄口径取 1H 级
- **env_feasibility**: 纯 OHLCV，自证可实现
- **registered**: 2026-10-12

## 1. 来源
TradingView Breakout 分类页采集；作者 vanchesz；策略（strategy）。

## 2. 判据摘录（官方描述）
- 水平位 = **上一根高周期K线的高/低点**（1H/4H/日/周/月可选）
- 三段式确认：追踪**首次触碰** → 等待K线**收盘**同时越过原始水平位**和**
  首次触碰极值 → 入场（"confirmation, not anticipation"）
- 即：突破需两次验证——破位收盘 + 超过回抽/回踩极值

## 3. 初评（阶段②，2026-10-12）
- 判据可量化性：高（三段式条件全部可操作化）
- 与 MLIB/S-001 关系：**与 H1/L1 结构高度同构**——M-PT-004"首次回调三条件"
  与其"first touch → confirmed close beyond first-touch extreme"是同一思想的
  两种表述；S-001 的 H1/L1+H2/L2 合并 detector 可视为其推广版
- **严格 vs 宽松预跑**（`strict_vs_loose.py`，前日高位 60m 代理、日末平仓、双边万3）：
  - 宽松（首根收盘越位）：n=9,639，**−0.022%**，胜率 43.3%
  - 严格（首触极值双重确认）：n=5,173，**≈0.000%**，胜率 39.3%
  - **判读**：双重确认方向正确（单笔质量 +2.2bp、样本减半），支持 RS004 的
    严格/宽松对照设计——但 60m 代理下两臂都不过成本线；正式裁决等 H1/L1
    detector 在基线管道中的同框对比
- 先验评级：🟡（同构方法，边际价值在于对照而非新信息）
- 适用场景：S-001 H1/L1 判据严格度对照臂；RS004 §严格/宽松对照

## 4-7. 待阶段推进
