# vnpy_patiming

PA 择时引擎（阶段一 + 二期信号 + 真实数据链路），实现对应
`docs/pa_timing/requirements-and-implementation-plan.md` v1.2。

## 模块

- `engine.PatimingEngine`：唯一 DB 写者。写入 API（CAS + canonical hash +
  配额 + 双周期校验 + key_levels 价格带 + 请求限速）、轮询对账、
  WARMING_UP/PAUSED 流转、K 线有效期倒计时、预警状态机、outbox 投递。
- `signals.detectors`：信号 #1/#2/#3/#4/#5(缺口简版)/#6 高2低2(trailing)/
  #7 双顶双底/#10 区间边缘反转；阈值集中在 `config.DEFAULT_CONFIG`。
- `delivery`：Redis Stream 投递 handler（protocol=2，at-least-once）。
- `adapters`：AkShare/新浪 1m 真实行情适配 + `warmup_engine` 历史预热。
- `replay`：point-in-time 回放评估器（T1/SL 标注、MFE/MAE、分信号胜率）。
- `audit`：LLM 翻译对账（原始需求 -> 指令 -> 报警 链条报告）。
- `mcp_service`：写入面 MCP（token 鉴权，source 服务端注入），基于 fastmcp。
- `app.py`：vnpy App 形态（tick -> BarGenerator 1m -> 引擎）。

## 契约要点

- **只预警、不入场**：信号在K线收盘确认 PA 形态后即为本系统终点；
  payload 的 trigger/stop/targets 均为**人工决策参考位**，TRIGGERED 仅表示
  参考关注位被触及，入场永远由人工完成。
- **全收盘基（D5）**：形态确认、失效判定、量化计算一律以K线收盘评估。
- key_levels 支持两套词表：引擎词表
  `prior_high/prior_low/range_top/range_bottom` 与选品词表
  `support/resistance`（入库自动映射），`swing_points` 忽略。
- 价格带校验：引擎已知最新价时，key_levels 偏离 ±10% 拒绝。
- `request_min_interval_s`：单来源请求最小间隔（默认 0 关闭，生产建议 1）。
- 报警 confidence 为规则分（信号族基准 + 实体 + 重叠度），确定性可复现。
- 决策定案（doc §13）：`signal.summary` 聚合事件（最佳机会 + 临期提醒，
  有变化才推）；跨周期同向 `multi_tf_confirmed=true` 且 confidence +0.1；
  不做自动续期（临期由 summary 提醒）；热更新维持任务重建。

## 真实数据验证（验收口径）

`tests/patiming/test_real_data_*.py` 使用真实新浪 1m 行情跑通：

1. MCP 协议层（fastmcp in-memory Client + token 鉴权）写入指令 ->
   真实数据预热 -> 真实突破 ARMED -> 真实触发 TRIGGERED ->
   LLM 对账链条报告。
2. 真实数据回放评估器：逐条预警 T1/SL 标注、MFE/MAE、分信号胜率。
3. 真实 Redis Stream 投递（本机实例 XADD/XREAD）。

合成数据测试仅作为逻辑单测存在，验收以真实数据套件为准。

## 快速开始

```python
from vnpy_patiming import PatimingEngine
from vnpy_patiming.adapters import AkshareOneMinuteFeed, warmup_engine

engine = PatimingEngine("patiming.db")
engine.register_delivery_handler(lambda event: print(event["event_type"]))
engine.start()
warmup_engine(engine, AkshareOneMinuteFeed().fetch_1m("RB0", "SHFE"))
engine.submit_instruction("strategy:demo", {...})  # 见 docs 契约
```

实弹冒烟（交易时段、需显式开启）：
`LIVE_SMOKE=1 python -m vnpy_patiming.live_smoke`

已知边界：指令热更新当前按任务重建处理（预热重来）；
CTP 实时链路在 vnpy 网关侧接入，本包不包含交易柜台连接。
