# Exhaustion Detector (YUHUNGTsai) — 方法论提取
来源: https://www.tradingview.com/script/aHH36PaR-Exhaustion-Detector/ (2026-10-12 经代理抓取)
状态: 官方描述完整恢复；Pine 源码本体需登录态未取（开源脚本，后续可人工登录复制）

## 官方描述（原文要点）
Detects potential trend exhaustion using volume spikes combined with rejection wicks.
Scoring system (0-6), four dimensions:
1. volume intensity relative to average   （量能强度 vs 均量）
2. wick length relative to body size      （影线长度 vs 实体）
3. candle close position                  （收盘位置）
4. prior trend context                    （前期趋势背景）
Score 4+ = standard signal; 5+ = strong signal.

Bullish Exhaustion (bottom): 下跌后，长下影 + 高量 + 收盘接近日内高位（卖方失去控制）
Bearish Exhaustion (top):    上涨后，长上影 + 高量 + 收盘接近日内低位（买方失去控制）
Volume-Price Divergence (DIV): 极端量 + 极小实体（多空拉锯）

信号: EXH↑/EXH↓ = 衰竭(4分); EXH↑↑/EXH↓↓ = 强衰竭(5+); DIV = 量价背离
特性: 任意品种/周期; 量能/影线/趋势参数可调; 实时评分面板; 内置警报

## 研究侧判读（QA+RES）
与 MLIB 衰竭族的本质差异：本指标是 **climax 衰竭**（放量+长影=消耗性冲刺），
我们的 M-EX-003/M-DV-001 是 **absorption 衰竭**（缩量探底=吸收）。
两种假说互斥但不相容——同一行情里可能只有一种成立。
=> 登记对照实验：climax-衰竭 vs absorption-衰竭 在同数据同阶段下的
   条件 IC/条件收益 head-to-head（无需基线，60m+GT 即可跑）。