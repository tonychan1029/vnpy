---
id: CAND-001
title: Exhaustion Detector（TradingView 社区衰竭类指标）
source: TradingView - Exhaustion Detector by YUHUNGTsai (script/aHH36PaR)
collected: 2026-10-12
category: 衰竭
impl_scope: 工具类（因子层，可降维至日内）
env_feasibility: 需替代（判据预期纯 OHLCV 可实现；当前阻塞是源码访问而非数据依赖，待工程侧解决后核实有无隐藏数据依赖）
heat_evidence: 检索命中，热度数据待源码页可达后补录
status: rejected
# 2026-10-12 双假说对照裁决：climax 衰竭（放量+长影）在 6 品种 60m 数据多头侧
# 全 horizon 负收益（n=357，RB/TA 重灾），核心假说不成立——拒绝引进；
# 副产品：自有 absorption 衰竭获独立验证（20 根 +0.057%，5/6 品种，M-EX-003 升温）。
# 详见 assets/CAND-001/h2h_exhaustion.md；未测空头侧；方法论存档保留
---

# 外部候选卡：Exhaustion Detector

## 1. 来源
- 平台/链接：TradingView script/aHH36PaR（区域域名访问受限，源码待取）
- 采集日期：2026-10-12

## 2. 判据摘录（2026-10-12 方法论完整恢复，原文见 assets/CAND-001/methodology_extract.md）
- **评分系统 0–6，四维度**：量能强度 vs 均量、影线长度 vs 实体、收盘位置、前期趋势背景
- 阈值：≥4 分标准信号，≥5 分强信号；另有 DIV（极端量+极小实体=量价拉锯）
- Bullish：下跌后长下影+高量+收盘接近日内高位；Bearish 对称
- **关键发现——与 MLIB 是两种衰竭假说**：本指标 = **climax 衰竭**
  （放量+长影=消耗性冲刺）；我们的 M-EX-003/M-DV-001 = **absorption 衰竭**
  （缩量探底=吸收）。互斥假说，同段行情可能只有一种成立
- **对照实验已登记**：climax vs absorption head-to-head（同数据同阶段条件 IC，
  无需基线，60m+GT 即可跑，验证队列新增）

## 3. 初评（阶段②）
- 判据可量化性：高（四维度均有明确量化口径）
- 与 MLIB 关系：**互补而非重复**（见 §2 关键发现）——M-EX-003 的缩量条件
  与本指标的放量条件在数据上将直接对撞
- 先验评级：🟡（climax 类衰竭指标社区常见，有效性待我们的数据裁决）
- 适用场景：RS001 ②衰竭判据的对照臂

## 4. 对照实验裁决（2026-10-12，assets/CAND-001/h2h_exhaustion.md）
climax vs absorption head-to-head（统一下跌背景+收盘上1/3口径）：
**absorption 全面胜出**（20根 +0.057%/5,972笔 vs climax −0.190%/357笔）。
外部指标拒绝引进；其副产品是自有 M-EX-003 获独立旁证。
## 5-7. 不适用（rejected，流程终止于阶段②）
