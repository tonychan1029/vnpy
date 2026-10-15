# HO004-B4 影响量化：DT/DB 背景对 reversal 标签的暴露

- 基线 signals_detail（v0 时代）逐笔按 v1 context_tags 归位；

## DOUBLE_BOTTOM（基线总量 17604）

| 窗口起点背景 | 笔数 | 占比 |
|---|---|---|
| range | 3473 | 19.7% |
| reversal | 2195 | 12.5% |
| breakout | 2674 | 15.2% |
| trend_strong | 5762 | 32.7% |
| trend_channel | 2290 | 13.0% |
| (空) | 1210 | 6.9% |

## DOUBLE_TOP（基线总量 17490）

| 窗口起点背景 | 笔数 | 占比 |
|---|---|---|
| range | 3531 | 20.2% |
| reversal | 2117 | 12.1% |
| breakout | 2704 | 15.5% |
| trend_strong | 5636 | 32.2% |
| trend_channel | 2257 | 12.9% |
| (空) | 1245 | 7.1% |

## 判读

- B4（背景 {range,reversal}→{range}）改动量：DB 2195/17604（12.5%）、DT 2117/17490（12.1%）——来自 reversal 标签窗的信号将不再触发；
- 若不改 B4（保留 {range, reversal_v2}），v2 reversal 触发 36.2% 将使 DT/DB 背景大幅扩面，信号总体显著膨胀——故 B4→{range} 是收缩性选择；
- 对 DB（optimizing 中）影响：基线 +0.086 的可比性被打破一部分，
  v2 标签基线重跑时 DB 分层报告须同时给新旧背景两组。
