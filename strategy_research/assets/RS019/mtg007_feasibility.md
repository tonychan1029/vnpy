---
id: RS019-MTG007-BTE
title: MTG007 输入：接力框架 v1.2 功能边界工程可行性与成本评估（BTE）
status: final（BTE 评估，供 MTG007 排优先级）
created: 2026-10-15
author: BTE（回测与工程）
related: [FRAMEWORK-RELAY v1.2, RS017, RS014, RS001, RS004, RS015, RS016, RS019, HO005, HO006, quant-repo/poolscan.py, quant-repo/pa/background.py, vnpy/vnpy_patiming, RS020/hermes_scripts/pullback_screen.py]
---

# MTG007 BTE 评估：接力框架 v1.2 功能边界——工程可行性与成本

> 评估范围：模板 v1.2（§2.3 四量化 / §2.4 五类择时信号 / §2.5 预警提前量 1/4 + RR≥1.6）。
> 代码基线：quant-repo（poolscan.py 1752 行、pa/background.py 361 行、pool_config.yaml）、
> vnpy/vnpy_patiming（signals/detectors.py 786 行、config.py、runtime.py）、
> RS020/hermes_scripts/pullback_screen.py（Hermes 四因子）。
> **路径勘误**：任务单所写 `D:\AIprj\quant-repo\strategies\pullback_screen.py` 不存在；
> 实际位于 `strategy_research\assets\RS020\hermes_scripts\pullback_screen.py`
> （Hermes/Linux 侧脚本，数据路径 `/home/tony/...`）——**不能直接 import 复用**，
> 只能移植其纯函数（zigzag/trend_h1/er_of，共约 120 行纯 Python，可移植性好）。

## 1. 选品层四量化可行性表

| # | 量化维度 | 现有代码已有什么 | 缺什么 | 工程量 | 状态 |
|---|---|---|---|---|---|
| 1 | **趋势形态**（波段高低点判趋势/区间） | `pa/background.py`：`_find_pivot_swings`（TradingView pivot + CCI 聚类 + HL 交替去重）+ `analyze_market_structure_and_zone`（HH/HL→BULL、LH/LL→BEAR、否则 CHOP_RANGING）；`pullback_screen.trend_h1` 有纯摆动点口径（不依赖均线） | **"区间"不是一等输出**：两个 scanner 对 CHOP_RANGING 一律 `no_trend` 跳过（poolscan.py:508/955），而 v1.2 要求"确认是交易区间还是趋势"并输出区间边界供用户行动 | **低-中**：解除 CHOP 跳过 + 补区间质量判据（摆动点≥2 高 2 低 + 边界往返次数）+ 输出 range_top/range_bottom 到 key_levels（patiming LEVEL_KEYS 已支持 range_top/range_bottom 词表） | 需修改 |
| 2 | **背景 PA 心态**（多头控盘/空头控盘/多空拉锯） | trend_state 三态：BULL_TREND≈多头控盘、BEAR_TREND≈空头控盘、CHOP_RANGING 粗对应拉锯；patiming context_tag 五值 {trend_strong, trend_channel, range, breakout, reversal} | **"拉锯"无独立语义**：CHOP_RANGING 是"非趋势"的兜底，不区分"区间有序（控盘边界清晰）"与"多空拉锯（控盘交替、摆动点交错、EMA 反复穿越）"；无 mood 分类函数 | **中**：新增 `classify_pa_mood()`（摆动点交错度 + close/EMA 位置占比 + EMA 穿越计数，~80-120 行）；判据校准依赖 RS012/RS015/RS016 context 研究（均在 review，未执行） | 需新增 |
| 3 | **回调位置三法** | ①波段高低点：✅ 已有（`nearest_support/resistance` = 参与趋势判定的最近摆动点，background.py:305-318）；③区间边界：部分——CHOP 分支取最近 swing high/low 兜底，patiming 层有 range_top/range_bottom | ②**K线密集区：全链路零实现**（选品/择时层均无价格聚类或成交量分布算法）；③边界稳定性依赖 RS016 strict_range 实验结论 | ①✅；③低-中（等 RS016）；②**中-高**（见 §4） | 部分实现 |
| 4 | **衰竭信号**（三推楔形/W底/M顶/量价背离/抛售高潮） | 择时层已有：WedgeThreePushDetector（三推幅度递减+实体衰减）、WmDetector（W底/M顶，默认关闭）、DoubleTopBottomDetector；研究侧 RS014/MLIB 有 climax/absorption/背离全套实证 | 选品层（大周期）无任何衰竭维度；量价背离 v1 检验未过（M-DV-001，6/6 品种负）；抛售高潮 fade 已被拒绝（CAND-001 rejected）；**信号层零使用 volume**（RS001 已记录此缺口） | 分项见 §3（楔形/WM 低-中可复用，量价类中-高） | 部分实现 |

**附带发现（工程卫生）**：`pa/background.py:103` `_run_state_machine` 引用了未在 `__init__` 定义的 `self.swing_multiplier`——一旦被调用即 AttributeError。当前主路径（`_find_pivot_swings`）不调用它，属死代码潜伏 bug，建议随下批改动删除或补参数。

## 2. 择时层五类信号映射表

引擎实况：`DETECTOR_CLASSES` 注册 **11 个** detector（9 类活跃 + h1_l1/w_m 默认关闭，`enable_h1_l1/enable_w_m=False`）；runtime 按任务单 `signal_categories` 启用矩阵路由（runtime.py:237），`ALL` 只映射 6 个 phase-1 类别。

| # | 用户信号 | 现有 detector 覆盖 | 缺口 | 需新增/改动 | 工程量 |
|---|---|---|---|---|---|
| 1 | 带量小平台收线突破 | BreakoutDetector：关键位收盘突破（实体≥0.6 + 位移≥0.1×ATR），**无平台前置、无量能条件**（passes_quality 的 overlap_mean 只是质量闸，非平台定义） | ①小平台整理前置判据（如近 N 根 overlap/宽度收缩）；②放量确认（volume z-score）——BarData 有 volume 字段、ctx.bars 可取，只是无人用 | 新增 PlatformVolumeBreakoutDetector（或给 Breakout 加前置钩子） | **中**（平台定义+量阈需回放校准，2-3 人日） |
| 2 | H2L2 | ✅ HighTwoLowTwoDetector（h2_l2，活跃）：趋势背景内相邻摆动点二次回调 + EMA 同侧 + 窗口约束，trailing 突破单 | 仅"武装"缺口：HO006-A1 后选品 `TREND_SIGNAL_CATEGORIES=["structure_pullback"]`，任务单默认不含 h2_l2 | 选品侧武装列表加 `h2_l2`（一行 + 单测断言，可与 HO006 同批） | **低**（0.5 人日） |
| 3 | 垂线/倒垂线 | RangeEdgeDetector._pin 有完整 pin bar 判据（影线≥2×实体 + 收盘位置），但**被锁死在 context_tag=="range" 且仅区间边缘触发** | 独立的 PinBarDetector（回调支撑/摆动点位置触发，不限 range） | 新增 detector，复用 `_pin`，加位置过滤（近 key_levels） | **低-中**（1 人日） |
| 4 | 反包K线 | RangeEdgeDetector._engulf 有吞没判据（同 index 双向去重已处理）；热线 LinuxSignalScanner 有裸吞没（MTG006 决议 A 退役中） | 独立 EngulfingDetector（方向化 + 位置过滤，趋势/区间均可用） | 新增 detector，复用 `_engulf` | **低-中**（1 人日） |
| 5 | 近均十字星小K线 | 最接近：EmaPullbackDetector（触及 EMA + 斜率定向，limit 单类型引擎已支持 order_type="limit"）——但该类别是 MTG004 已否决武装项；十字星/小 K 判定无实现 | 新增 DojiNearMaDetector：小实体（body_ratio/bar_length 已有结构函数）+ 距 EMA≤k×ATR + 破均线限价触发 | 新增 detector | **中**（1-2 人日；**研究风险见 §7**） |

**新 detector 的固定接入成本**（每类都要做）：detectors.py 新类 + `DETECTOR_CLASSES` 注册 + `config.SIGNAL_CATEGORIES` 加类别（engine.py:321-324 校验依赖此集合）+ `REASON_DEFAULT_SIGNALS` 映射 + 选品武装列表 + 单测。约 0.5 人日/项的注册开销，schema/DB 零改动（signal_categories 为 JSON 文本）。

## 3. 衰竭信号现状与补齐方案

研究积累盘点（RS014 三轮实验 + MLIB + RS001 + RS004）：

| 用户信号 | 研究积累 | 可复用度 | 补齐方案 | 工程量 |
|---|---|---|---|---|
| 三推楔形 | 现网 WedgeThreePushDetector（幅度递减 wedge_decay_ratio=0.67 + 实体衰减）；RS001 §2.1 提议升格为"回调质量度量" | **高**（代码现成） | 选品层复用：把检测逻辑抽为共享函数对 60m/日线结构跑（现锁定 context_tag=="reversal"，选品侧需放宽或独立入口）；或先作 context 标注非触发 | 低-中 |
| W底/M顶 | WmDetector 已实现（RS004 §2 判据、HO002 移交、颈线+衰竭证据+wash 容差），**默认关闭**；RS019 环节1 佐证：CHOP+贴近 raw 口径 +20 日 +0.45%（区间反转方向有正证） | **高**（代码+研究双全） | 开关 `enable_w_m=True` + 观察期校准 + 与双顶底去重逻辑已内建（runtime.py:260）；选品层复用同楔形路径 | 低 |
| 量价背离 | M-DV-001 **v1 检验未过**（6/6 品种 20 根均负），v2≈0 并入 M-EX-003；信号层 volume 零引用（RS001 记录）；期货量能换月扰动需按 DEC006 处理 | **中**（有实证边界，无可用代码） | 按 M-EX-003 absorption 口径重新操作化（三重边界：仅多头/上升回调或浅调/前置闸门 prior_ret20>−5%）；需新因子模块 + 量能复权管道 | **中-高**（研究先行） |
| 抛售高潮 | CAND-001 climax 假说**已被 h2h 实验拒绝**（全 horizon 负，fade 顶部不付钱）；absorption 胜出且样本外存活（holdout +0.183%） | **低**（结论方向相反） | ❌ 不应作为独立触发信号实现；✅ 可复用 `code/analysis/exhaustion_h2h.py` 的事件判定逻辑，降级为**上下文标注**（"climax 事件"文案），仅在 M-EX-003 边界内提示 | 中（标注器）+ 研究先行 |

**结论**：五类衰竭信号中 2.5 类（楔形/WM/部分 climax 标注）可低成本复用；量价背离必须按 M-EX-003 边界重做；抛售高潮按现有证据**不可做 fade 触发**。

## 4. K线密集区实现方案（回调位置三法②）

现状：选品/择时/研究侧均无实现，是四量化中唯一的**空白算法**。

**推荐方案 A（摆动点价格聚类，先做）**：
1. 输入：`PABackgroundEngine().get_pure_swings()` 已确认摆动序列（60m 30 天 ≈ 240 根或日线 120 根）——与现有管线同源、as-of 安全、无复权/量能依赖；
2. 聚类：价格按 0.25×ATR 分箱（或 tick 整数倍），相邻箱合并 → 候选区 [zone_low, zone_high]；
3. 显著性：触及次数 ≥ k（初值 3，含高低点各计入一次）、近期加权（指数衰减半衰期 ~20 根）；
4. 输出：现价下方最近显著区 = `confluence_support`（上方镜像），写入 PoolEntry.key_levels 新键；
5. 回调判定：三法取并集（摆动点 ✓ / 密集区 ✓ / 区间边界 ✓ 任一命中即"回调到位"），reason_code 记录命中方法。

**方案 B（成交量分布/Value Area，后做）**：按 bar 量分布到价格箱取 POC/Value Area 边缘作密集区。**前置依赖**：DEC006 量能治理（换月对量的扰动）——量连续性未修复前 B 的输入不可信。

**成本**：算法本身 ~120-150 行 + config 阈值 + 单测 = **中（1-2 人日）**；真正的成本在**有效性验证**——阈值（箱宽/次数/衰减）需要历史回放校准，可直接复用 rs017 回放框架（`rs017_trendpullback_replay.py` 判据复刻路径现成）做"密集区支撑 vs 单摆动点支撑"的后续走势对照。建议按 RS016 预注册模式先出实验设计再实现，**总成本 中-高**。

## 5. 选品预警提前量（区间 1/4）改动点

| 改动点 | 位置 | 内容 |
|---|---|---|
| 配置 | `pool_config.yaml [scan]` | 新增 `warn_band_ratio: 0.25`（区间高度占比） |
| MarketPullbackScanner | `poolscan.py _evaluate_symbol`（~L998-1012 RR 计算段旁） | long：`close - support <= ratio*(resistance-support)`；short 镜像。当前触发条件是"15m MA20 贴近"，**与区间位置无关**——需决定并列（AND 收紧）还是替代（OR 放宽）；建议：band 作为**主触发**，near_ma 降为加分项，否则两条件交集过稀 |
| TrendPullbackScanner | `poolscan.py evaluate_product`（~L512-526） | 同样加 band 判断（entry_limit=EMA20 与边界位置解耦，band 判定用 close 对 support/resistance） |
| 过滤统计 | `SCAN_REASON_LABELS` | 加 `not_in_warn_band`（区间中段不入池的通知文案），诊断面板自动生效 |
| 通知/契约 | 零改动 | payload 已携带 support/resistance/rr_ratio/entry_limit，满足 §2.4a"有经验用户可直接行动"标准 |
| 择时引擎 | 零改动 | 任务单消费端不感知触发几何 |

**自洽性校验**：1/4 带内入场 + 边界止损 + 对侧边界目标 ⇒ RR≈3.0；中轨目标 ⇒ RR≈2.0——与 RR≥1.6 底线天然一致，两规则无冲突。**工程量：低**（~20 行 + config + 单测 + 影子对比一轮）。

## 6. RR≥1.6 门槛改动影响范围

**配置层（真·改几行）**：
1. `market_min_rr: 1.0 → 1.6`（market_pullback，poolscan.py:879 读取）；
2. `min_rr: 1.5 → 1.6`（trend_pullback，poolscan.py:471 读取）——**注意是两个键**，模板 §2.5 只点名了 market_min_rr；
3. `monitors.signal_k.min_rr: 1.5`（SignalKMonitor.interests 独立闸门）——池内条目已 ≥1.6 后此闸不 binding，建议顺手对齐 1.6 保持口径单一。

**非配置影响（治理面）**：
- **通过率下降**：RS017 smoke（1.0 门槛下）rr_too_small 已占 17/177≈10%，提到 1.6 剔除量显著增大；入池稀缺是设计意图但需在观察期口径中预设预期；
- **观察期基线断裂**：selection_tracking.jsonl（HO006-A2）的 KPI 在改前/改后不可直接对比——需在跟踪文件记录 `config_version` 或以部署日为界分段统计；
- **RR 口径脆弱性仍在**（RS017 §2.2：support/resistance=最近两摆动点，随结构重画）——1.6 是**数字达标**，不解决"RR 的实际含义随摆动点距离漂移"的问题；密集区支撑（§4）落地后 RR 分母才有稳定口径；
- **治理登记**：ENVIRONMENT R10 登记 + 与 HO005/HO006 同批部署（同文件域 poolscan.py，无冲突）。

**结论**：代码改动≈一行×2-3 键（**低**），但"只改一行"的说法不完整——影响范围=两个配置键+监控器对齐+基线分段+R10 登记。

## 7. 优先级排序

### 立即可做（工程证据充分，低成本，可随 HO005/HO006 同批）
| 项 | 工程量 | 理由 |
|---|---|---|
| ① RR≥1.6（两键+监控器对齐+R10+基线分段） | 低 | 用户已定调；纯配置；风险=通过率下降，观察期本来就要求重置口径 |
| ② 预警提前量 1/4 带触发 | 低 | 改动点明确（两 scanner 各一处+config+文案）；与 RR 规则数学自洽；择时零改动 |
| ③ H2L2 武装（signal_categories 加 h2_l2） | 低 | 引擎 detector 现成且活跃，只缺选品侧武装一行 |
| ④ 垂线/倒垂线 + 反包K线 两个新 detector | 低-中 | `_pin`/`_engulf` 判据现成可移植；注册开销固定；先小周期观察期运行再谈扩大 |

### 需研究先行（算法可写，但判据/阈值未经历史验证，直接上生产属未验证放宽——QUANT_HANDOFF D9 教训）
| 项 | 工程量 | 理由 |
|---|---|---|
| ⑤ K线密集区（方案 A） | 中-高 | 唯一空白算法；先按 RS016 预注册模式出实验设计→rs017 回放框架验证阈值→再进 poolscan |
| ⑥ 背景三分类（多空拉锯） | 中 | 分类函数可写，但"拉锯"判据校准依赖 RS012/RS015/RS016 context 研究（均在 review 未执行）；避免双轨定义 |
| ⑦ 带量小平台收线突破 | 中 | 平台定义 + 量能阈值需回放校准；volume 进 detector 无管道障碍（BarData 自带），但阈值为占位时勿投产 |
| ⑧ 量价背离（按 M-EX-003 口径） | 中-高 | v1 已被证伪，须按 absorption 三重边界重做 + 量能复权管道（DEC006 前置） |
| ⑨ 趋势/区间双输出（CHOP 一等公民） | 低-中 | 代码小改，但区间质量判据依赖 RS016 strict_range 结论（预注册待评审）；T_NEAR 20 日 −0.54%（RS019 环节2）说明趋势侧口径本身待修，先修口径再加输出 |
| ⑩ 近均十字星小K线 | 中 | **判据与已否决的 EMA 接刀形态同族**（RS019 环节2：趋势+EMA20 贴近 20 日负超额）——差异点（十字星确认 vs 触及即武装）需先小样本验证，否则重蹈 MTG004 |

### 暂缓（现有研究证据方向相反或依赖未解冻项）
| 项 | 理由 |
|---|---|
| ⑪ 抛售高潮作为选品/择时触发 | CAND-001 climax 被 h2h 实验有据拒绝（fade 全 horizon 负）；仅允许降级为 M-EX-003 边界内的上下文标注，不做触发 |
| ⑫ W底/M顶全面放开 | 非暂缓"实现"而是暂缓"扩大"：代码现成，先按现网观察期跑 enable_w_m 小范围校准（与 RS016 同期），避免与双顶底通知语义重叠期放大误报 |

### 排序逻辑一句话
先做"零研究依赖的配置/小改"（①-④）让 v1.2 定调的两条硬规则（1/4 提前量 + RR1.6）与两个免费信号（H2L2/垂线/反包）当周生效；所有"新算法/新阈值"（⑤-⑩）一律走"预注册实验→历史回放→影子运行→投产"四步，防止再次出现 market_min_rr 2.0→1.0 式的未验证放宽。

## 8. 附：评估依据文件清单

| 文件 | 用途 |
|---|---|
| quant-repo/poolscan.py | 两 scanner 触发链、RR 读取键、武装常量、HO005-A1 重检已落地确认 |
| quant-repo/pa/background.py | 摆动点/趋势/边界现状；`swing_multiplier` 潜伏 bug 发现 |
| quant-repo/pool_config.yaml | market_min_rr=1.0 / min_rr=1.5 / signal_k.min_rr=1.5 实值确认 |
| vnpy/vnpy_patiming/signals/detectors.py + config.py + runtime.py | 11 detector 实况、启用矩阵、category 注册成本 |
| RS020/assets/hermes_scripts/pullback_screen.py | 四因子脚本实况（Linux 路径、纯函数可移植） |
| RS014 + assets/MLIB + RS001 + RS004 | 衰竭信号证据链（CAND-001 rejected / M-DV-001 未过 / M-EX-003 边界 / WM 判据） |
| RS015/RS016/RS019 assets | context/区间研究在途状态；T_NEAR 负超额证据 |

> 修订记录：2026-10-15 初版（BTE，供 MTG007）。
