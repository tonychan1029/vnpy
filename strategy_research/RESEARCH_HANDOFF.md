# 研究侧交接记忆胶囊 · 策略研究体系（2026-10-15 更新）

> 维护规则：每会话结束必须更新本文件与 STATUS.md 与 STRATEGY_TABLE.md（策略台账）；
> 上下文不稳时以本文件 + STATUS.md + STRATEGY_TABLE.md 为准，勿凭记忆。
> 对位文件：工程侧 QUANT_HANDOFF.md（根目录）。

## 治理（最高约束，违反即事故）
- **目录权限（用户 2026-10-15）**：策略研究目录（strategy_research/）权限只限策略研究；
  **所有涉及项目工程的修改（文档与代码均含），必须通过开发角色实施**——研究侧可经
  管线（HO 移交单）协调、可在 HO 中附代码建议/集成规格/回归测试集，但**严禁直接修改
  任何工程文件**（quant-repo 源码、106 生产机文件、根目录工程文档）
- **合并与版本提交权（用户 2026-10-15，同日裁决修订）**：研究产出的有价值
  方法/代码库模块/策略，merge/rebase/历史改写与仓库其余范围仍归开发工程；
  **研究侧获授权对 strategy_research/ 路径自主阶段性 commit**（约束：先刷新
  后提交+pytest 全绿+只 commit 不 push）——制度见 HOUSEKEEPING_清理与版本
  管理.md
- **提交前先更新先刷新（用户 2026-10-15）**：提交代码前必须先更新（pull/update）
  先刷新（重读当前状态），防止多团队并行修改导致冲突覆盖——工程侧拾取 HO 实施
  合并时适用；研究侧任何共享文件操作前同样先重读当前状态
- **预注册阈值精确值纪律（用户批准 2026-10-15，HO004-B3 教训）**：预注册验收
  阈值禁止取自报告舍入显示值，必须以精确值（≥6 位小数）落档；验收 runner 须
  内置锚自检（对照臂同跑阈值，锚不过线=阈值校准问题非交付问题）
- **评审验收制**（用户 2026-10-14）：所有用户策略新增/修改，工程实施后必须经研究侧
  评审验收（按 HO 预注册标准跑 runner）；验收不通过 → 按 HO 条款回滚或整改
- **交付价值评估制**（用户 2026-10-14）：研究输出转工程交付必须附《交付价值评估》——
  预期收益/工程成本/不交付的代价/替代方案/明确建议；无评估不出单
- **接力框架分工边界**（TEMPLATE v1.2 冻结）：
  - **选品层（大周期）四量化**：①趋势形态（波段高低点→趋势/区间）②背景 PA 心态
    ③回调位置（支撑三法：波段高低点/K线密集区/区间上下边界）④衰竭信号（三推楔形/
    W底/M顶/量价背离/抛售高潮）
  - **择时层（小周期）**：只做入场信号量化——带量小平台收线突破/H2L2/垂线倒垂线/
    反包K线/近均十字星（挂破均线限价）；一个择时策略监控全部选品池
  - **选品预警 ≠ 入场信号**：选品=提前发现（区间高度 1/4 范围内即预警，不等触达边界）；
    有经验用户收到通知（品种+方向+关键位）可自行挂单；精确入场由择时层/用户判断
  - **RR 准入底线 ≥1.6**（用户确认，低于不触发——区间中段入场最危险，正确入场应在
    边缘 1/3 以内）；生产 `market_min_rr: 1.0 → 1.6`（ENVIRONMENT R10，待工程部署）
  - 多选品并行、持续新增；交易模式=智能选品+择时预警+**人工下单**（程序化冻结）
- **研究决议传导义务**：研究否决的信号类别不得继续出现在生产武装列表——传导走 HO
- **生产在运策略纪律**：quant-repo 与 ~/.vntrader 只读；评估/优化/退役走 MTG+用户签批
- **环境分层**：本机 Windows=开发测试；106 生产机=生产运行（SSH webserver106 只读）
- **多智能体专家组默认**（重大研究/管理议题）：先例 MTG006（QA/RISK/BTE）、
  MTG007（boundary-review + feasibility 两个 subagent）；团队 teammate 名额已满（8），
  用 subagent 代替
- **中国期货市场微结构特征**（用户 2026-10-15 固化，策略设计基本盘）：①大量大幅度
  高低开；②频繁打损前低前高后迅速拉回（stop hunting——前低/前高是猎杀区非支撑区）；
  ③突破后不回调单边走到位。**策略设计必须利用这些特征产生利润，而非用教科书假设
  对抗市场现实**（TEMPLATE 定调⑧）
- **量化验证方法论**（用户 2026-10-15）：形态/信号量化准确性=**先视觉检验**（图表
  标注叠加肉眼对照，quantlib.visual.plot_with_overlays），**再同周期回测**（信号在
  60m 触发→量 60m 后续 N 根胜率/盈亏比，不跨周期）；大品种（RB/CU/TA）排除操纵噪音
- **外部方法论来源**（用户 2026-10-15 指令，不闭门造车）：从量化社区/交易社区/技术
  量化书籍找方案（中美都行）——已检索：AL_price_action（Al Brooks PA Python 实现）、
  chansdk/chanlun-pro（缠论量化）、arXiv 止损猎杀预测/价格极值 ML 分类/OHLCV 信号
  结构性限制论文（详见 STATUS 外部检索节）
- 用户纪律（累计）：决策类先问再做；负结果如实入档；实施须独立评审；流程先审后做；
  佣金按 DEC003 双边万3（用户确认维持）

## 环境
- 数据：`D:/AIprj/tradereplay/data`（**只读**）。5m 2009-03 起 17 年全历史（六大所 97
  品种）；60m 6 主连 RB/CU/AG/M/MA/TA（2015–2026）；day 91 品种（2005→2026）；1m 全
  市场 91 品种仅 1 个月前向采集（2026-09-07 起）；无 tick。**5m/60m/day 均为未复权
  直拼——收益研究必须先做后复权（DEC006 D-2：`splice_adjust`，已封装于
  rs020_merge_backtest.py，坏点护栏跳过局部比值 0.5 外/≥2.0）**
- 外盘：106 生产机有 COMEX 金银/WTI/标普/美元采集——本机无
- venv：`.venv\Scripts\python.exe`；quantlib 测试：`-m pytest strategy_research/code/quantlib/tests -q`（**50 项全过**）；研究管线旧测试：`-m pytest strategy_research/code/tests -q`（15 项）
- 外访：TradingView 经代理 `curl.exe -x http://127.0.0.1:7890`；matplotlib 中文=Microsoft YaHei（visual.py 已配置）

## 当前状态（2026-10-15 下午更新）
- **🔴 RS020 勘误两处（2026-10-15 下午，修正后结论维持）**：①臂2 节点过滤
  `b[0]<=node_dt` 索引错误（恒真→60m 趋势过滤全程用数据末端 300 根=前视
  泄漏）；②trend_h1_60m 浅拷贝原地平滑（跨节点变异共享行）。修正后重跑：
  **臂2 OOS +20日 +0.85%（n=106，50.0%）**、臂3 逐位不变 +0.76%（n=87）→
  **合并方向成立维持**（两臂均 >0 且 >臂1 −0.64%）；臂2 long OOS +0.72%
  （n=34）；管线互证=臂2 long 与臂4 新脚本 4a 逐位一致。详见 RS020 §7.5.1
- **RS019 臂4 hybrid v3 完成（inconclusive）**：干净重写（修旧版夜盘归属/
  前瞻窗口/索引漂移），预注册=臂2∩60m 多头准入 + 4b mom6 确认（60m 平滑）
  + 4c M-EX-003 回调到位吸收确认（h2h 原口径+无前视收盘实证）+ 4d 双确认；
  **4d OOS n=2 < 护栏 30 → 样本不足，主判读不可下结论**（不宣称有增量也
  不否决）；quant 积分第三层挂起（公式档案未落盘）；路径建议（需预注册+
  批准）：扩池 / 60m 节点对齐 / 吸收确认窗口化
- **HO004 验收已执行：B1/B2 PASS，B3 边界伪影待用户裁决**——B1 reversal
  32.7%/LR 1.06 ✅；B2 四变体均 ≥25% ✅；B3 阈值 31.8% 取自舍入显示值
  （精确 0.317684 连 v1 锚不过线），v2 与锚逐位一致+差分仅 trend↔reversal
  占位迁移 → 非退化实质成立；复核报告
  assets/RS015/ho004_acceptance_review_20261015.md（推荐 A：实质通过落档）
- **HO004+HO005 部署核实（106 只读）**：2026-10-14 22:25 用户授权提前窗口
  执行成功（DEPLOY_OK/preflight 6/6）；四服务 active；HO005 功能标记在位；
  R10 min_rr 仍 1.0（随 HO006 2026-10-16 04:15 部署）；工程已排期
  HO006+HO007r2-gateway（10-16）——**HO007 工程侧已推进至 r2 阶段**；
  HO005 正式验收=待工程单测/集成记录归档 + 下次真实换月生产观察
- **签批全部完成**：MTG006 决议 A/B/C+立即干预（热线退役启动/60分钟观察期带 KPI/
  择时 RegimeSwitch 启用前先议退役——106 核实未挂实盘）；DEC006 数据分层 final；
  §9 复核单 final；HO005 换月处理 final（**已于 10-14 22:25 部署**）；HO006
  武装列表修正+入选跟踪 final（10-16 部署）；HO007 quantlib 工程集成 final
  （工程侧执行中，r2 阶段）
- **量化工具库 quantlib 建成（strategy_research/code/quantlib/）**：6 模块 ~25 函数，
  **50/50 单测通过**——
  - structure.py：摆动点（fractal+交替合并）/趋势判定双方案（zigzag HH/HL、EMA 斜率+
    HH/HL，classify_trend 统一接口）/区间边界（swing/percentile）/支撑三法（near_support/
    near_resistance/kline_density_zone）
  - gap.py：缺口检测（simple/ATR）/回补判定/分类（breakaway/runaway/exhaustion/common）/
    缺口转关键位（用户问询后新增；缺口定位=结构/关键位类，非 K 线信号）
  - pullback.py：回撤比例/MA 贴近/关键位接近/支撑守住
  - entry_signal.py：突破确认/H2L2/pin bar/反包/近均十字星（**显式参数接口** o/h/l/c，
    消除索引混淆）
  - exhaustion.py：楔形三推/量价背离（价跌量缩=看涨已修正）/抛售高潮
  - visual.py：K 线+标注叠加图（RB 60m 视觉检验已通过）
  - **教训已固化：全模块 I_* 常量块（I_DT..I_OI=range(7)），禁止硬编码索引**——本轮
    实证索引漂移 3 种方式（8 元素布局混入、条件写反、行列读反），修复 2 个真实函数
    bug（find_range_boundary 支撑/压力颠倒、exhaustion 索引错位）
- **核心研究结论**（详见 STRATEGY_TABLE + 各 RS 报告）：
  - RS019：60 分钟引擎判据 OOS 偏负（−0.64%）；方向判定反向+回调触发无增量——
    **但评估口径已修正**：选品层是提前预警不是入场信号，负结果仅否定"选品日收盘
    即入场"用法
  - RS020：Hermes 四因子判据 OOS 转正（🔴勘误修正口径 **+0.85%，n=106**
    vs 引擎 −0.64%；原 +0.78% 系前视泄漏口径）→ 合并方向成立；
    臂4 hybrid v3 已执行（inconclusive，见上）
  - RS021：全市场日线波段选品（91 品种 17,515 事件，Hermes 日线档判据）OOS +20 日
    +0.37%（52.0% 胜率）通过初步门槛；score≥80 高分子集 +4.49%；成本后不可存活
    → 建议 shadow 试点非直接上线；deep_dive.md 已产出
- ** Relay framework TEMPLATE v1.2**：§2.3 选品四量化权威定义 / §2.4 预警提前量+
  定位 / §2.5 RR≥1.6 / 定调⑧ 市场微结构
- **NOTE 知会单**（60_decisions/NOTE_HO003验收结果与HO004拾取_20261014.md）已更新
  覆盖 HO003-HO007 全部移交内容，粘帖即用 → 工程对话

## 关键实证边界地图（每格有档案，禁区=有失败实验背书）
| 方法/信号 | 有效范围 | 禁区 |
|---|---|---|
| mom6 突破段溢价 | 持仓期属性（B>A） | 入场时机✗ |
| M-EX-003 absorption | 独立 60m 多头衰竭判据 | 空头✗ 深跌✗ 叠加✗ |
| M-TR-002 trend_score | 跨品种排序 | 独立方向信号✗ |
| M-DV-001 量比背离 | 已撤销 | 反转判据永久✗ |
| RER 边缘反转 | strict_range 20 根口径正 | T1=2R 可交易口径✗（RS016 终止）|
| EMA20 回调入场 | — | MTG004 否决（−0.202，12/12 年负）——HO006 已从武装列表移除 |
| 明牌基准 | 及格线=扣费后为正 | 三族≈零毛边际 |

## 文件地图（新增部分）
- **`RESEARCH_ROADMAP_策略研究中期计划_2026Q4-2027Q1.md`：中期计划（2026-10-15
  用户指令立项）——六主线+M1-M6 里程碑，方向级修订需用户批准**
- `code/quantlib/`：量化工具库（structure/gap/pullback/entry_signal/exhaustion/visual
  + tests/ 50 项）——**研究侧已确认可用，HO007 final 待工程集成**
- `code/analysis/`：+rs021_daily_swings_replay.py / rs021_deep_dive.py /
  rs021_visual_check.py / **rs019_hybrid_backtest.py（v3 干净重写，2026-10-15
  已执行 inconclusive）** / ho004_acceptance.py / **ho004_b3_boundary_diag.py
  （B3 边界诊断）** / ho004_acceptance.py 复核报告见 assets/RS015/
- `assets/RS019/`：+merge_hybrid_backtest.md（臂4 v3 结果，2026-10-15）+
  mtg007_boundary_review.md + mtg007_feasibility.md（BTE 优先级：
  立即=RR1.6/1/4带/H2L2 武装/垂线反包；研究先行=密集区/三分类/平台突破/量价背离v2；
  暂缓=抛售高潮触发/WM 扩大；附 pa/background.py:103 死代码缺陷）
- `assets/RS021/`：daily_swings_drawdown.md + deep_dive.md + visual_check_RB60m.png +
  visual_check_CU60m.png
- `assets/RS015/`：+ho004_acceptance.md（runner 机械判读）+
  ho004_b3_boundary_diag.md（边界诊断）+
  ho004_acceptance_review_20261015.md（复核+裁决请求）
- `60_decisions/`：+DEC006 final / HO006 final / **HO007 final（quantlib 集成）** /
  NOTE v2（HO003-HO007 全量）

## 待办（依赖驱动）
1. **HO008 签批（用户）**：审计缺陷修复与传导闭环移交单（draft）——A 组
   P0（R10 min_rr 1.6 补部署/StructurePullback 空头/SecondBreakout 单位/
   D11 守卫/配置卫生/LLM 残留）+ B 组 P1 + C 组 P2；签批后转 final 发工程
2. **研究侧自查（RES，HO008 平行）**：methods 量纲/trend_score 方向/阈值
   统一/quantlib wedge 死参/bar[4]/M-EX-003 约束代码化；RS021 台账勘误
   （score≥80 统一 deep_dive 口径 n=451/+4.49% 并标注重尾）；CAND-007 降级
   gated；RS016 确认触发臂预注册；H2L2/FAKE_BREAKOUT 处置议题列 MTG007
3. **HO005 验收收尾**：工程单测/集成记录归档（研究侧复核）+ 下次真实换月
   生产观察（最终验证）
4. **RS019 臂4 后续路径（待用户裁决，问卷在途）**：窗口化吸收确认（推荐预
   注册后跑）/ 暂缓转 BTE 优先级 / 扩池 10 主连；用户问询"5 品种依据"已答
   （=生产池 10 主连 ∩ 本地 60m 可得，AL0/Y0/P0/SR0/IF0 无 60m，见
   ENVIRONMENT §1 + RS017 §5.2.2）；
   quant 积分第三增量层待公式档案归档后补测
5. **HO006/007r2 部署验收**：HO006 已于 10-15 15:12 提前部署（武装列表/
   TTL/传导修复生效）→ 研究侧验收复核；HO007r2-gateway（10-16 04:05）→
   部署后回归断言
6. **RS019 优化方向落地**（按 BTE 优先级）：垂线反包
   detector 移植 / K线密集区（摆动点聚类）/ PA 三分类（拉锯语义）/
   平台突破 detector / 量价背离 v2（M-EX-003 口径）/ 近均十字星差异化验证
7. **外部方法论深挖**（用户指令"不闭门造车"）：AL_price_action（Al Brooks PA Python）
   / chansdk·chanlun-pro（缠论分型笔中枢）/ arXiv stop-hunt 预测 + 价格极值 ML +
   OHLCV 信号结构性限制论文——评估可移植方案
8. **档案缺口补齐**：quant_gap_analysis.md + hermes_scripts/ 落盘
   assets/RS020/（臂4 quant 层与 Hermes 对照依赖）
9. **用户侧**：热线 7 日通知确认窗（退役 vs 升级）
10. **15m 波段选品**：受 1m 数据仅 1 个月制约，前向积累中
11. 季度：重验证登记册按触发条件执行

## 佣金与成本口径
- **DEC003（现行，用户确认维持）**：佣金 = 保证金 × 万3 双边——基线与后续复算统一此口径
