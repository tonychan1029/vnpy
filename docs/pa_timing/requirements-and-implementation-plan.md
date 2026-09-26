# PA 择时引擎：需求与技术实施方案

版本：v1.3
日期：2026-09-25
状态：评审修订后定稿（决策点已经多角色评审定案）

评审修订（v1.3，决策记录见 §13）：聚合摘要、多周期置信度加成、续期策略、热更新策略四项决策点定案。

评审修订（v1.1）：指令字段所有权与 CAS、canonical content_hash、K线有效期精确定义与预热不倒计时、数据面降级链、目标价推导、审计事件表与推送 outbox、tick/bar 双层失效、MCP 服务端注入身份、回放 point-in-time、信号规则消歧。

评审修订（v1.2）：进程写入边界（引擎单写者）、复合主键 (source, instruction_id) 与越权防护、poll 降级触发模式、PAUSED 时 ARMED 预案处置、对账谓词覆盖非 ACTIVE 状态、报警合并规则、双周期写入校验、REVOKED 终态语义、outbox 投递契约（目标 / 顺序 / 幂等）。

---

## 1. 背景与目标

本项目是价格行为学（Price Action，下称 PA）交易系统的择时子系统。系统整体分层：

```
选品层（策略扫描 / 人工需求 + LLM 转换）
        |  写入结构化指令
        v
监控池指令表（控制面，持久化）
        |  引擎轮询拾取
        v
择时引擎（实时监控 + 信号量化 + 预警推送）
        |  结构化预警事件
        v
下游（执行模块 / 通知 / 回测记录）
```

核心边界约定：

- 背景分析与选品属于上游，**择时引擎不做背景判断**，只按指令对监控池内标的做实时监控、量化信号识别与预警。
- 监控池不是品种列表，而是"**品种 × 入选原因**"的监控任务集合。同一品种可同时因多个原因在池中，各自盯不同的信号。
- 择时引擎输出的是**结构化择时预警**（挂单预案 + 全生命周期状态），不是直接下单指令；执行由下游完成。

## 2. 总体架构

### 2.1 控制面与数据面分离

- **控制面**：监控池指令表。多来源写入（选品策略、LLM via MCP），引擎轮询读取。指令表是唯一事实来源。
- **数据面**：择时引擎。由指令驱动监控任务的生命周期，任务内跑信号检测与预警。

### 2.2 指令来源

| 来源 | source 标识 | 说明 |
|---|---|---|
| 选品策略 | `strategy:<name>` | 多个策略可并存，各写各的指令 |
| LLM（MCP） | `llm:<session>` | 外部 LLM 通过 MCP 工具写入，含人工需求转换 |

选品策略成熟前，主链路为：人工给出需求（自然语言）→ LLM 转换为结构化指令 → MCP 写入指令表。

## 3. 监控池指令表

### 3.1 表结构与字段所有权

```sql
-- 生产者字段（upsert 写入面；SQL 展示为逻辑分组，物理同一张表）
timing_instruction
  instruction_id      TEXT NOT NULL     -- 来源方生成，幂等键；复合主键 (source, instruction_id)
  producer_revision   INT NOT NULL      -- 生产者单调递增修订号，CAS 依据
  desired_status      TEXT NOT NULL     -- ACTIVE / REVOKED，生产者唯一可请求的两个状态
  source              TEXT NOT NULL     -- 服务端按认证身份注入（见第 8 章），模型不可自报
  symbol              TEXT NOT NULL     -- vnpy 全代码，如 rb2501.SHFE
  selection_timeframe TEXT NOT NULL     -- 选品周期，有效期按它计
  exec_timeframe      TEXT NOT NULL     -- 执行周期，信号检测在它上面跑
  context_tag         TEXT              -- PA 背景标签，决定启用矩阵
  signal_categories   JSON              -- 启用信号枚举数组或 "ALL"
  direction           TEXT              -- long / short / both，缺省 both
  key_levels          JSON              -- 可选上游关键位；缺省引擎本地补摆动点
  params              JSON              -- 参数覆盖，一期对 LLM 锁死为默认
  priority            INT
  reason_code         TEXT NOT NULL     -- 入选原因枚举（见 3.3）
  reason_note         TEXT NOT NULL     -- 人话摘要：原始需求 / 入选依据
  valid_bars          INT NULL          -- 有效期，单位 = 选品周期K线根数，缺省 12
  valid_until         TEXT NULL         -- 可选墙钟硬上限，与 valid_bars 取先到
  content_hash        TEXT              -- 引擎识别内容变更

-- 引擎字段（运行面，生产者不可写）
  status              TEXT NOT NULL     -- ACTIVE / WARMING_UP / PAUSED / REVOKED / EXPIRED / INVALID
  feedback            TEXT              -- 引擎回写：校验错误、运行状态、等待生效原因等
  effective_from      TEXT              -- 回写：实际生效时刻
  anchor_bar          TEXT              -- 回写：生效锚点K线时间（选品周期）
  expires_bar         TEXT              -- 回写：预计到期K线时间（重启恢复 / 展示）
  remaining_bars      INT               -- 回写：剩余根数，LLM / 人可查
  created_at / updated_at
```

设计要点：

- **CAS 更新**：同 `(source, instruction_id)` 的修改必须携带严格递增的 `producer_revision`；小于等于已存值则拒绝并回写错误。revoke 也是一次携带 `desired_status=REVOKED` 的 upsert，且只能作用于**自己 source 名下**的指令——不存在旁路覆盖，也不存在越权操作他来源指令。
- **所有权强制**：写入层剥离报文中出现的引擎字段（记录告警，不应用）；引擎写运行状态时只动引擎列，业务字段不受影响。
- **canonical content_hash**：参与 hash 的字段 = 全部生产者业务字段 + producer_revision；排除全部引擎字段与 created_at/updated_at。规范化：键字典序排序、UTF-8 紧凑 JSON、缺失与 null 等价、时间统一 ISO8601 + Asia/Shanghai、价格按交易所 tick 精度规整为字符串。算法 SHA-256，由写入服务统一计算，客户端不自行计算，杜绝两端 hash 不一致误判"变更"。
- **feedback 回写**：校验失败、订阅失败、ARMED 数量、等待生效等写回指令行，LLM 与人可随时查闭环结果。
- **INVALID 不丢弃**：仅用于写入通过基础校验、对账时发现深层问题（如品种不在白名单）的行；**数据不可用是 PAUSED + feedback，不是 INVALID**。schema 非法在写入服务直接拒绝，不落业务行。
- **历史只增不删**：撤销是改状态，不物理删除。保留"原始需求 → 指令 → 产出报警"全链条用于审计与评估。
- **PAUSED 语义**：引擎独占（数据不足 / freshness gate 失败 / 品种无行情），恢复后自动回原路径；生产者只能请求 ACTIVE 或 REVOKED。

### 3.2 指令状态机

```
写入校验通过 -> ACTIVE 落库（desired_status=ACTIVE）
写入校验失败 -> 拒绝，不落业务行，错误返回调用方
引擎拾取，基础设施未就绪 -> WARMING_UP（历史预热，不倒计时）
  | 预热完成 -> 运行中（锚定倒计时，feedback 回写）
  | 数据不足 / freshness gate 失败 -> PAUSED（回写原因，恢复后自动回运行路径）
  | valid_bars 归零 / valid_until 到点 -> EXPIRED（引擎自动）
生产者 revision 递增重写 -> 热更新（引擎重审 ARMED 预案）
生产者 desired_status=REVOKED -> REVOKED（终态：复活必须换新 instruction_id；同 id 更高 revision 的 ACTIVE 重写一律拒绝并记 REJECT 审计）
对账发现深层问题（品种不在白名单等）-> INVALID（错误回写，可修正后重写 id 复活）
```

运行时 `status` 由引擎独占写；生产者的 ACTIVE / REVOKED 是"请求"，由引擎一次性落到 `status` 并记审计事件。任务被撤销 / 过期时，其名下 ARMED 预案统一转 `cancelled_by_instruction` 终态并推送，下游可清账。

### 3.3 入选原因枚举与默认信号矩阵

| reason_code | 含义 | 默认 context_tag | 默认启用信号 |
|---|---|---|---|
| BREAKOUT_WATCH | 突破蓄势观察 | breakout | 1 / 2 / 3 |
| TREND_FOLLOW | 趋势延续跟踪 | trend_strong / trend_channel | 4 / 5 / 6 |
| RANGE_FADE | 区间边缘回归 | range | 7 / 10 / 2 |
| REVERSAL_WATCH | 反转观察 | reversal | 7（8 / 9 占位） |
| DISCRETIONARY | 人工盘感跟踪 | LLM 从描述推断 | 按描述指定 |

引擎只认 `context_tag + signal_categories` 跑启用矩阵；`reason_code / reason_note` 用于审计与报警文案。选品策略成熟后由策略程序填写，人工期由 LLM 填写，schema 不变。

### 3.4 审计与推送事件落库

- **timing_instruction_event**（append-only）：id、instruction_id、producer_revision、event_type（CREATED / UPDATED / STATUS_CHANGED / REVOKED / EXPIRED / INVALID / WARMING_UP / PAUSED / RESUMED 等）、from_status、to_status、actor（producer / engine）、payload_snapshot（JSON）、ts。主表只存当前态，全过程审计靠事件表，可完整回答 ACTIVE→PAUSED→ACTIVE→EXPIRED 这类路径。
- **timing_alert_event**（append-only）：alert_id、event_type、from_lifecycle、to_lifecycle、payload_snapshot、ts。报警全生命周期留痕。
- **alert_outbox（推送发件箱）**：id、event_type、payload_json、delivery_status（pending / delivered / failed）、attempts、next_retry_at、last_error、created_at、delivered_at。状态变更与事件落库同一事务；推送网关异步消费 outbox 投递，失败指数退避重试，超限标 failed 并告警。杜绝"先改状态再推 webhook"造成的状态与通知不一致。

### 3.5 持久化与进程写入边界

- **引擎 App 进程是数据库唯一写者**。指令行写入、状态机流转、审计事件、outbox 生成与投递状态更新，全部由引擎进程在事务内执行；MCP 写入服务与推送网关不直接写库。
- **MCP 写入服务**：进程内完成鉴权、配额、校验后，将写请求经引擎内部接口（本地 RPC / 队列）提交，由引擎事务执行并同步返回结果；"拒绝并回写错误"同样是引擎侧一次写，CAS 天然串行化。
- **推送网关**：从引擎领取 outbox 批次（内部接口），投递后回传结果，由引擎批量更新 delivery_status。
- **兜底约定**：SQLite 开 WAL、busy_timeout ≥ 5000ms、事务短小；写入压力超限时整体迁移 MySQL / Postgres，DAO 走 peewee 保持可移植，引擎内部写接口不变。

## 4. 有效期机制（K 线时间）

有效期按**选品周期的完成K线根数**倒计时，不按墙钟。理由：交易时段不连续（午休、隔夜、节假日、夜盘有无），墙钟 timedelta 会把非交易时间算进去；K 线驱动则没有K线就不计数，节假日、停牌、午休自动跳过，无需交易日历。

### 4.1 规则

- 默认 `valid_bars = 12`（选品周期K线根数）。60m 选品即 12 根 60mK线。
- **认知对齐**：国内商品期货单日交易时间约 5.5~6.5 小时，60m × 12 约跨两个交易日，不是自然日一天。这是特性不是 bug。
- `valid_until`（墙钟）为可选硬上限，与 `valid_bars` 同时存在取先到；两者都缺省用默认根数。
- **锚定**：预热完成后写 `effective_from`；锚点取当时进行中的选品周期K线；不足一根的锚点K线不计入，倒计时从其后第一根完整K线收盘起算。tick 层 ARMED 跟踪在预热完成后立即开始。
- **盘外写入**：非交易时段到达的指令保持 ACTIVE，feedback 回写"等待下一交易时段生效"，开盘首根K线出现才正式锚定。
- **预热不倒计时**：`WARMING_UP` 期间 `valid_bars` 不消耗，倒计时自预热完成后锚定起算；指令不会"还没机会 ARMED 就过期"。
- **重启恢复**：同时持久化 `expires_bar`（预计到期K线 open_time）与 `remaining_bars`。重启后首个活K线收盘时若 open_time 已越过 `expires_bar` 则立即过期；时间对不上则以 `remaining_bars` 计数为准。K 线时间戳只做恢复加速，不当唯一事实。
- **停牌**：无K线倒计时自动暂停，视为特性写入文档。
- **行情断流 / 数据不足**：freshness gate 检测到数据缺失或过期时任务转 PAUSED（见 5.4），不消耗有效期，恢复后继续；彻底失联由运维层告警，不混入指令语义。
- **双时钟命名隔离**：指令有效期用选品周期计（`valid_bars`）；单条 ARMED 预案自身超时用执行周期计（`expire_bars`）。字段名与文档严格区分。

### 4.2 选品周期K线的精确定义

- **合成来源**：倒计时用选品周期K线必须由引擎从 1mK线合成（vnpy BarGenerator），不得直接采用 datafeed 原生周期K线——各源合成规则可能不一致，会引入分歧行为。
- **时间语义**：K线以 open_time 标识，交易所本地时区 Asia/Shanghai；夜盘K线按其自然 open_time 计。倒计时只依赖 open_time 单调递增的K线序列，不做交易日归属换算。
- **完成判定**：窗口内收到 ≥1 根 1m 且下一窗口首根 1m 到达时，前一根完成；会话最后一根按 open_time + interval 墙钟兜底完成（防悬挂）。无数据的窗口不产生K线，倒计时自动暂停（与停牌语义一致，防止把断流时间计入有效期）。
- **重启补偿**：以持久化的 `remaining_bars` 计数为准（见 4.1），`expires_bar` 仅作快路径与展示；重启不需要回补历史K线来恢复倒计时。

## 5. 择时引擎运行机制

### 5.1 双层监控循环

- **K 线收盘层（信号识别）**：每根执行周期K线收盘后，对池内全部标的跑一遍信号检测，产出 / 更新挂单预案。**识别一律在收盘后**，保证确定性。
- **收盘层（触发跟踪，D5 全收盘基）**：触发位/失效位均以K线收盘评估——收盘穿越触发位即 TRIGGERED（不可逆）；收盘穿越失效位即 INVALIDATED；tick 不参与信号语义（D7：tick 仅作兜底合成的K线原料）。原 tick provisional（at_risk/restored）机制自 D5 起停发。
- **到期管理**：预案带 `expire_bars`（执行周期，缺省 3 根），超时未触发自动转 EXPIRED 并推送。
- **跳空约定**：开盘跳空越过触发位按触发处理，标记 `gap_open=true`，成交价按开盘价报告下游。
- **降级触发模式**：`data_mode = akshare_poll`（无 tick）时，触发与 provisional 失效判定降级到 1m 收盘驱动——语义不变、粒度变粗；payload 必带 `data_mode` 字段（ctp_tick / akshare_poll），下游按数据粒度决定执行策略。

### 5.2 轮询对账（reconciliation）

轮询间隔 2~5 秒（可配），每次增量对账：

1. 读 `status IN (ACTIVE, WARMING_UP, PAUSED)` 的指令集：ACTIVE 参与任务 diff；WARMING_UP / PAUSED 保留任务、只走预热与数据健康巡检路径，不进入"消失"分支（防止重启后非 ACTIVE 任务被误杀）。
2. 与运行中监控任务做三类 diff：
   - **新增**：创建监控任务——按 5.4 降级链订阅行情，初始化品种+执行周期的K线合成器 / ATR / 摆动点缓存 / 位管理器，按 `signal_categories` 注册检测器；预热完成判据（配置化）：exec 历史 ≥ max(3×ATR 周期, 10) 根且选品周期 ≥ 1 根，达标前任务处 WARMING_UP，不产出信号、不倒计时。
   - **变更**（同 instruction_id 但 content_hash 变了）：热更新参数与信号开关；已有 ARMED 预案重审，不再合规的走失效流程。
   - **消失**（REVOKED / 过期）：停任务；同品种+周期还有其他指令覆盖（引用计数 >0）则只摘掉该指令贡献，行情订阅与公共缓存保留；否则取消订阅。名下 ARMED 预案转 `cancelled_by_instruction` 并推送。
3. 周期扫描过期：有效期到点即使生产者不删，引擎也自动停。
4. 数据健康巡检：freshness gate 检查最后行情时间戳，缺失 / 过期 → 任务 PAUSED + feedback 回写原因，同时名下 ARMED 预案统一转 cancelled（原因 `data_pause`）并推送——数据缺口期间的触发位不可信，恢复后靠重新识别重建预案。

### 5.3 多来源冲突处理

- **任务按指令隔离，资源按品种共享**：每条指令一个独立信号任务（各自方向偏好、信号集、参数），共享底层行情订阅与指标缓存。对账简单、溯源清晰。
- **报警层去重合并**：同一根K线上不同指令产出预案时，仅当 `signal_id + direction + 规整后 trigger.level` 三者一致才合并为一条，payload 的 `instruction_ids` 带全部来源；参数（buffer、key_levels、有效期）不同导致挂单价不同的预案各自独立推送。下游看到干净信号，内部可溯源。

### 5.4 数据面降级链（MVP 硬约束）

引擎不假设 datafeed 永远可用，复用 poolscan 已验证的降级语义（quant-repo/poolscan.py `refresh_subscriptions`）：

```
CTP 合约解析（AkShare OI / 1m OI 判主力）
  -> 失败且 poll/auto 模式允许时：AkShare 连续合约 1m 轮询（AKSHARE_POLL 网关）
  -> 历史 1m 拉取做预热（ATR14 / pivot / 位管理器就绪）
  -> freshness gate（最后行情时间戳阈值检查）
```

任一环节数据不足：任务 PAUSED + feedback 回写原因，名下 ARMED 预案转 cancelled（原因 `data_pause`），恢复后自动走 WARMING_UP → 运行中。禁止把数据问题标成 INVALID。

### 5.5 推送一致性（outbox）

**投递目标**：Redis Stream（下游订阅）为主，可选 webhook 转发适配器。**语义**：at-least-once，下游按 `event_id` 幂等去重。**顺序**：同一 alert_id 的事件严格按落库序投递（outbox 按 alert_id 分组消费，重试不跳序）；跨 alert 不保证全局顺序。所有事件先落 alert_outbox（与状态变更同事务，见 3.4），网关异步投递，失败指数退避重试，超限标 failed 并告警；delivery_status 更新经引擎代写（3.5）。对外语义：下游以收到的事件为准驱动自身状态，引擎状态库与事件流永远可对账。

## 6. 信号体系与量化规则

### 6.1 量化标准

"可量化"的标准：规则完全确定性、两人独立实现结果一致、不依赖肉眼判断。做不到的信号只占位不实现。

### 6.2 公共算法基座

1. **摆动点检测（point-in-time）**：fractal / pivot，左右各 k 根（k=2 起步），输出带强度的 swing high / low 序列；每点带 `pivot_bar_time`（坐标时间）与 `confirmed_bar_time`（右侧 k 根收齐后的确认时间）。信号只允许使用 `confirmed_bar_time ≤ 当前K线收盘` 的摆动点，杜绝未来函数。
2. **关键位管理器**：接收上游 key_levels，每位带状态 `fresh / tested / broken / expired`（收盘穿越即 broken，超 N 根自动 expired）。所有信号位有效性统一从这里查。
3. **K 线统计**：ATR(14)、body_ratio（实体/全长）、近 5 根平均重叠度。
4. **事件记忆**：失败突破日志（供信号 3）、同标的同方向 ARMED 去重。
5. **回放评估器**：历史回放 → 全部 ARMED 事件 → 自动标注前瞻结果（N 根内先到 T1 还是 SL、MFE / MAE）→ 分信号命中率与盈亏比报告。评估必须 point-in-time：只能使用当时已确认的信息（含摆动点确认时间），禁止使用重放完毕才可知的数据。

### 6.3 信号清单总表

统一记号：ATR = ATR(14)，body_ratio = 实体/全长，buffer = N tick，容差默认 0.25×ATR。信号编号全文复用。

| # | 信号 | 检测条件 | 挂单 | 止损 | 失效 | 阶段 |
|---|---|---|---|---|---|---|
| 1 | 关键位突破 | 收盘穿越 key_level，方向与背景一致；body_ratio≥0.6；收盘越位≥0.1×ATR；全长≤3×ATR | 突破单 @ 信号K线极值+buffer | 信号K线另一端 或 key_level∓0.25×ATR 取更远 | 收盘回到关键位内侧 | 一期 |
| 2 | 假突破反转 | K线刺破关键位≥0.05×ATR 且收盘收回内侧 | 反向突破单（多空触发公式见 6.4） | 刺破极值±0.25×ATR | 收盘再穿出关键位 | 一期 |
| 3 | 二次突破 | 近 N 根（缺省 10）内有同方向失败突破事件（#2），当前收盘满足 #1 全部条件 | 突破单同 #1 | 同 #1 | 同 #1 | 一期 |
| 4 | EMA20 回调 | 趋势背景下 low≤ema≤high 或 收盘距 ema≤0.25×ATR，方向随背景 | 限价单 @ ARMED 时冻结的 EMA±buffer | 趋势方向最近确认 pivot 高/低点∓0.25×ATR；距离>2.0×ATR 拒绝出预案 | 收盘穿越回调起点；或指令背景失效 | 一期 |
| 5 | 结构位/缺口回调 | 触及前低/前高/缺口沿±容差；缺口=open>前根high，后续 M 根内未回补才算有效位 | 限价单 @ 关键位内侧±buffer | 关键位外侧 0.25×ATR | 收盘有效穿越关键位 | 一期（缺口简版） |
| 6 | 高2/低2 | 执行周期近 6~10 根内两个相邻 pivot 低（高）点，第二个不破第一个（容差 0.1×ATR），都在 EMA 正确一侧；消费 6.2 统一摆动点流 | 突破单 @ 最新完成K线极值+buffer（逐根刷新） | 第二个回调点 | 收盘跌破第二个回调点 | 二期 |
| 7 | 双顶/双底 | 两个摆动极值差≤0.3×ATR、间隔≤M 根（20~60 校准）；第二次测试出现上冲失败或反转K线；颈线=两极值间最低/最高摆动点 | 突破单 @ 反转K线极值（颈线方向） | 双顶/双底外侧 | 收盘突破双顶/双底外侧 | 二期 |
| 9 | 楔形三推 | ZigZag（ATR 阈值）分段，三段推幅 p3<p2<p1，第三推 body_ratio 衰减 | 反向突破单 @ 衰竭K线极值 | 第三推极值±容差 | 价格再创第三推新高/新低 | 三期（实验开关，默认关） |
| 8 | 趋势线突破+回抽 | 趋势线拟合多解、不可复现 | — | — | — | 占位不实现 |
| 10 | 区间边缘反转 | 仅 range 背景：触及区间边缘±容差 + 反转K线 | 限价单 @ 边缘内侧，或反转K线出现后改突破单 | 边缘外侧 0.25×ATR | 收盘穿出区间 | 一期 |

### 6.4 一期信号补充规则

- **#1 边界情况**：同方向多位重合取最近/最外位只报一个；跳空穿越收盘已越位时，突破单挂信号K线高点仍成立，正常流程。
- **#2 与 #1 互斥**：收盘在内侧即假突破，外侧即真突破，不双报。连续多根假突破只推第一次，后续并入 #3 计数。影线恰好触位不算刺破（必须≥0.05×ATR）。
- **#4 限价锚定**：ARMED 时冻结 EMA 值为挂单价，不做移动限价，保证回测 / 实盘一致；价格偏离时自然过期，可接受。
- **#2 反向突破单触发公式**：上沿假突破（收回收回内侧）→ 做空，`trigger = sell stop @ signal_bar_low − buffer`；下沿假跌破收回 → 做多，`trigger = buy stop @ signal_bar_high + buffer`。方向由假突破发生在位的上沿/下沿决定，不依赖背景标签。
- **#4 止损距离上限**：止损挂最近确认 pivot 外侧 0.25×ATR；若该距离 > 2.0×ATR（`max_stop_atr` 参数），视为止损结构过远，质量门拒绝出预案，不做移动止损硬夹。
- **#6 摆动流一致性**：高2/低2 必须消费与 #5 / #7 / #9 同一条摆动点流（同一 k、同一确认规则），禁止各检测器私有实现，避免同类结构在不同信号里定义漂移。
- **#10 反转K线定义（写死）**：pin bar = 影线≥2×实体且收盘位于K线外侧 1/3；吞没 = 实体完全包住前根实体且方向相反。同根K线触双沿只报一个；收盘穿出区间则预案失效且该沿转 broken。

### 6.5 背景 × 信号启用矩阵

| context_tag | 启用信号 | 方向限制 |
|---|---|---|
| trend_strong | 4 / 5 / 6 + 1（顺势） | 只顺势 |
| trend_channel | 4 / 5 / 6 | 顺势优先，通道极限点可逆势 |
| range | 7 / 10 + 2 | 边缘双向，中部否决 |
| breakout | 1 / 2 / 3 | 突破方向 |
| reversal | 7（8 / 9 实现后启用） | 反转方向 |

矩阵为目标态；实际可用性以 6.3 阶段列为准，未实现信号一律不注册检测器（一期 reversal 背景合法但暂不产出预案，feedback 提示）。

### 6.6 信号质量门（出预案前统一过滤）

- 信号K线全长 ∈ [0.5×ATR, 3×ATR]（太小无意义，太大止损成本高）。
- 止损距离 ≥ 0.5×ATR，且到 T1 目标盈亏比 ≥ 1.0。
- 近 5 根K线平均重叠度低于阈值（动能过滤）。
- 同标的同方向已有 ARMED 预案时去重不重复推；"更强"一期定义为固定信号族优先级表 + 更新时间新者优先，满足者走 REPLACE（原预案转 replaced 并推送）。

### 6.7 目标价推导（RR 质量门与回测的前置）

一期统一用 R 倍数目标，保证 RR 过滤与回放评估可计算：

- `risk = |entry_price − stop_price|`；突破单 entry 取 trigger.level，限价单 entry 取限价位。
- `T1 = entry ± 1.0 × risk`，`T2 = entry ± 2.0 × risk`（加减方向随 direction），payload 写**绝对价格 + ref**（`ref = "risk_multiple:1.0R" / "risk_multiple:2.0R"`），见 7.3。
- 结构性目标（区间高度投影、测量移动）作为后续增强预留：targets 允许追加第三项 structural（带 ref），一期不启用。

## 7. 预警状态机与输出契约

### 7.1 信号生命周期

```
DETECTED -> ARMED（挂单预案生效，等触发）
  -> TRIGGERED（挂单位被触及）
  -> INVALIDATED（价格穿越失效位）
  -> EXPIRED（expire_bars 超时）
  -> REPLACED（被更强信号覆盖）
  -> cancelled_by_instruction（指令被撤 / 过期）
```

预警不是一次性事件而是状态机：信号识别 ≠ 可入场，下游每条预警都带状态与失效条件。

### 7.2 推送事件类型

| event_type | 语义 |
|---|---|
| signal.armed | 挂单预案生成：挂什么单、挂哪、何时作废 |
| signal.triggered | 挂单位触及，可执行的时刻 |
| signal.invalidated | 价格穿越失效位 |
| signal.expired | expire_bars 超时 |
| signal.replaced | 被更强信号覆盖 |
| signal.cancelled | 指令被撤 / 过期连带取消 |
| signal.at_risk | tick 层穿越失效位，provisional 失效（预案保留，等收盘确认） |
| signal.restored | 收盘收回失效位内侧，provisional 清除，ARMED 继续 |

所有事件先落 alert_outbox 再异步投递（5.5 / 3.4）。at_risk / restored 保证 tick 长影线不会无声地杀死或复活预案，下游全程可见。

### 7.3 报警消息 schema

```json
{
  "event_type": "signal.armed",
  "schema_version": "1.0",
  "event_time": "2026-09-25T10:35:02",
  "payload": {
    "event_id": "TIM-20260925-000123",
    "instrument": "rb2501.SHFE",
    "exec_timeframe": "5m",
    "bar_time": "2026-09-25T10:35:00",
    "context_tag": "breakout",
    "signal_family": "secondary_attempt",
    "signal_id": "BREAKOUT_KEY_LEVEL",
    "direction": "long",
    "order_type": "stop",
    "trigger": { "type": "cross_above", "level": 3450.0, "buffer_ticks": 2, "ref": "signal_bar_high" },
    "stop": { "level": 3441.0, "ref": "signal_bar_low", "distance_atr": 0.65 },
    "targets": { "t1": { "price": 3459.0, "ref": "risk_multiple:1.0R" }, "t2": { "price": 3468.0, "ref": "risk_multiple:2.0R" } },
    "invalidation": { "type": "close_below", "level": 3438.0 },
    "lifecycle": "ARMED",
    "expire_bars_exec": 3,
    "confidence": 0.72,
    "gap_open": false,
    "data_mode": "ctp_tick",
    "source": "llm:session-abc",
    "instruction_ids": ["INS-001", "INS-007"],
    "admission_reason": { "code": "BREAKOUT_WATCH", "note": "用户：盯着 rb 突破前高" },
    "context_snapshot": { "ema20": 3436.2, "atr14": 5.8, "config_version": "cfg-2026-09-20" }
  }
}
```

字段设计约定：

- **trigger / stop / invalidation 全带 `ref`**：说明数字怎么算的（信号K线极值、结构位、ATR 倍数），下游与回测可复现。
- **`distance_atr` 内置**：下游做仓位管理与信号过滤无需再算波动。
- **targets 为绝对价格 + ref**：按 6.7 规则推导，RR 质量门与回放评估直接可算，下游无需二次推导。
- **`confidence` 占位**：一期规则打分（背景强度+K线质量+位置重合度），后续换统计胜率，结构不变。
- **失效条件必填**：预警生成即确定作废条件。
- **`data_mode` 必填**：ctp_tick / akshare_poll，标记触发判定粒度（见 5.1 降级触发模式）。
- **溯源必填**：`source` + `instruction_ids` + `admission_reason`，报警文案可读出"因什么原因监控、触发了什么"。

## 8. MCP 接口设计（LLM 入口）

三个工具，约定 `schema_version`：

- **`timing_instruction_upsert`**：写入 / 更新指令。服务端严格校验：品种格式与交易所白名单、周期枚举、signal_categories 枚举、有效期窗口合法性（valid_until > now + 最小存活时间）、双周期关系（selection_interval ≤ exec_interval 且 valid_bars × selection_interval ≥ 2 × exec_interval，否则指令必然在首个可识别信号前过期）、单来源并发指令数上限。
- **`timing_instruction_revoke`**：按 instruction_id 撤销（内部是一次 `desired_status=REVOKED` 的 upsert）。
- **`timing_instruction_query`**：查活跃指令 + feedback + 近期报警摘要；按 instruction_id 返回"原始需求 + 当前状态 + 已产报警列表"。

**身份与安全（不可信任模型自报）**：

- `source` 由 MCP 服务端按**认证身份**注入，请求报文中出现 source 一律剥离并告警；模型不能决定自己是谁。
- 写入面必须是**独立带鉴权的服务**（token per caller）。现有 `services/mcp_bridge.py` 是无鉴权的只读 Redis 快照桥（查询指标 / 池 / 信号），不得在其上原地扩展写工具；新建独立写入服务承载 upsert / revoke / query。
- 配额：单 session 指令数上限、活跃指令总量上限、文本字段（reason_note 等）长度上限、请求频率上限。
- 合理性检查：key_levels 各价位必须在最新价 ±X%（参数化）内，否则拒绝或要求留空；params 一期对 LLM 锁死默认，不许改阈值。
- 一期 LLM 指令直接 ACTIVE 生效；`require_approval` 开关位预留，未来加人工审核队列不改 schema。

## 9. 人工需求 → LLM → 指令转换契约

LLM 翻译规则收紧为契约，避免多 session 多写法：

- **必填**：symbol（白名单校验）、selection_timeframe、exec_timeframe、reason_code、reason_note（必须保留人的原始意图摘要）。
- **推断**：context_tag 从描述推断；signal_categories 缺省按 3.3 默认矩阵；direction 缺省 both。
- **默认值兜底**：人没说周期 / 有效期时，LLM 应向人确认；确认不了落默认值并在 reason_note 注明假设（如"周期未指定，默认5m；有效期未指定，按默认12根"）。
- **受限项**：key_levels 只在人明确给价位时才填，否则留空由引擎本地补摆动点；params 一期对 LLM 锁死默认。
- **有效期**：LLM 可传 valid_bars（选品周期根数）或 valid_until（墙钟），都不传引擎按默认。
- **闭环动作**：upsert 后必须回查 feedback，并向人结构化复述——监控什么、盯什么信号、方向、有效期、入选原因。校验失败自纠重试。人可随时 revoke。

## 10. 质量评估闭环

### 10.1 信号质量回放评估器

所有阈值参数（body_ratio、ATR 倍数、窗口 N、容差）不定死值，靠数据校准：

- 历史回放 → 全部 ARMED 事件 → 每事件自动标注前瞻结果（N 根内先到 T1 还是 SL、MFE / MAE）。
- 输出分信号命中率与盈亏比报告，指导参数调整。
- 一期上线用默认参数，但每个参数必须可被评估器数据校准。
- 评估与实盘共用同一检测代码路径与同一摆动点确认语义（point-in-time），禁止单独维护一套"离线版规则"造成双实现漂移。

### 10.2 LLM 翻译质量对账

选品策略不成熟期，系统质量瓶颈在"人话 → 指令"翻译环节。指令历史只增不删，保留三样东西对账：人的原始需求文本 → LLM 落的指令 → 产出的报警。评估维度：

- 翻译是否走样（品种、方向、周期、有效期）。
- 哪类 reason_code 产出的报警质量高，反过来调整枚举与默认矩阵。
- 未来选品策略上线时，用人工指令历史分布设计入选条件。

## 11. 实施计划

阶段一（MVP）：

1. 指令表（字段所有权 + CAS + canonical hash）+ 审计事件表 + alert_outbox + 轮询对账器（vnpy App 骨架，SQLite / peewee 持久化）。
2. 监控任务生命周期：数据面降级链（CTP → AkShare 1m → 历史预热 → freshness gate）、订阅管理、K线合成（选品周期从 1m 合成）、位管理器、point-in-time 摆动点检测、ATR 统计、WARMING_UP / PAUSED 流转。
3. 独立 MCP 写入服务（upsert / revoke / query）+ 鉴权、配额、合理性校验。
4. 一期信号检测器：#1 / #2 / #3 / #4 / #5（缺口简版）/ #10，含 6.4 消歧规则与 6.7 目标价推导，跑通 DETECTED → ARMED → 触发/失效（tick provisional + bar confirmed）→ outbox 投递全链路。
5. 有效期引擎：K线倒计时、预热不倒计时、锚定、重启恢复、自动过期。
6. 验收口径（DoD）：CAS 与 canonical hash 的 golden 测试；K线合成跨会话用例（夜盘 21:00~23:00 衔接次日日盘、会话末根墙钟兜底收线）；provisional / confirmed 双层失效的长影线用例；poll 降级模式的 1m 驱动触发用例；outbox 重试与同 alert 顺序用例；重启恢复（remaining_bars / expires_bar）用例；PAUSED → cancelled → 重建链路用例。

阶段二：

1. 信号 #6（高2/低2 状态机版）与 #7（双顶/双底聚类）。
2. 回放评估器上线，开始参数校准。

阶段三：

1. 信号 #9 楔形三推（实验开关，默认关）。
2. 信号 #8 趋势线重新评估是否用回归拟合+触摸计数的严格定义实现。
3. confidence 从规则打分升级为统计胜率。

工程形态：vnpy 独立 App（如 `vnpy_patiming`），含 MainEngine 接入、指令表 DAO、轮询对账线程、监控任务运行时、信号检测器注册表、事件推送网关、MCP 工具服务。

## 12. 边界与非目标

- 不做背景量化：背景标签与关键位来自上游指令，引擎不做趋势/区间判断。
- 不直接下单：输出预警与挂单预案，执行由下游完成。
- 不做仓位管理：只输出止损距离（ATR 口径），仓位计算在下游。
- 不做行情断流自愈：由运维层行情健康监控兜底。

## 13. 决策记录（多角色评审定案）

| # | 决策点 | 结论 | 理由 |
|---|---|---|---|
| D1 | 报警聚合摘要 | 明细照发；新增 `signal.summary` 聚合事件（每标的×方向仅保留最高 confidence 的最佳机会，附 remaining≤3 的临期指令提醒），状态有变化才推送，初始空态不推 | 下游二选一消费（明细 or 摘要）；不丢明细可回溯；空态噪声抑制 |
| D2 | 多周期置信度合并 | 不跨周期合并明细；同标的跨周期同向同时 ARMED 时，confidence +0.10（上限 0.95）并在 payload 标记 `multi_tf_confirmed=true` | 不同周期属独立信号，保留溯源；加成保留一致性收益 |
| D3 | 有效期自动续期 | 维持生产者显式重写；不引入自动续期 | 防僵尸监控；状态可解释；临期由 summary 提醒 |
| D4 | 指令热更新 | 维持任务重建（确定性优先） | 实现简单、可回放；预热成本成为实盘痛点再上增量重审 |
| D6 | 基础数据驱动 | 1m K 线为唯一驱动（全收盘基 D5）；tick 不进信号计算 | 测试=实盘同构；数据稳定性优于 tick 流 |
| D7 | 1m 中断兜底 | 1m 获取失败/过期 -> 切 T口 tick 仅作K线合成原料（不产生 tick 级信号）；恢复后切回 | 实盘可用性；tick 永不进信号语义 |
| D8 | 双模式状态管理 | REPLAY/LIVE 显式模式：差异仅时钟源（虚拟/系统）与数据到达节奏；引擎逻辑零分支（时间一律经 engine.clock()）；调度线程仅 LIVE，REPLAY 下 start() 禁止 | 全逻辑全流程回放=实盘同构；批量快照轮询器（实盘）与逐根喂入（回放）为仅有的两端差异 |

D8 附属——隐藏系统时间依赖清单与规则：
latest 型接口（新浪分钟/快照/主力清单）只在真实"现在"有意义 -> REPLAY 禁用，
仅消费调用方传入的历史K线；墙钟字段（valid_until）在 REPLAY 中自动剥离；
新鲜度类过滤（日线 age、freshness gate）必须以显式 now 参数实现；
Redis TTL / universe 缓存 / preflight 属 LIVE-only 组件。
4. 容量与扩展假设：一期单实例、监控池上限（建议 ≤100 标的）；超限演进按 symbol 分片多实例（引擎有状态，需按品种路由请求），二期按实际池规模决策。
