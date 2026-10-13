# 研究侧交接记忆胶囊 · 策略研究体系（2026-10-13 下午）

> 维护规则：每会话结束必须更新本文件与 STATUS.md；上下文不稳时以本文件 + STATUS.md + MTG004 纪要为准，勿凭记忆。
> 对位文件：工程侧 QUANT_HANDOFF.md（根目录）。

## 治理（最高约束，违反即事故）
- 活动范围**仅限 strategy_research/** 内：文档、方法库、研究级代码（文件头标 `# RESEARCH ONLY - 未获用户批准不得正式运行`）
- 未经用户显式批准：不正式运行任何策略、不推荐新策略转工程、不改边界外文件（含 QUANT_HANDOFF.md——本轮起用户授权"转交工程=写 HO 拾取通知进胶囊"此类动作，逐次确认）
- 跨边界交付走 **HO 移交单**（60_decisions/，用户批准 → final → 工程侧拾取；本轮 HO003 由工程直接自拾取并实施）
- 用户纪律（累计）：决策类先问再做；负结果如实入档；实施须独立评审；流程先审后做

## 环境
- 数据：`D:/AIprj/tradereplay/data`（**只读**）。60m 主力连续 6 品种 RB/CU/AG/M/MA/TA（2015–2026，换月后复权拼接由工程 baseline 口径处理）；1m 全市场 91 品种仅 1 个月前向采集（2026-09-07 起）；**无 tick 数据**
- venv：`.venv\Scripts\python.exe`；回归：`-m pytest strategy_research/code/tests -q`（15 项全过）
- 外访：TradingView 经代理 `curl.exe -x http://127.0.0.1:7890`（web_fetch 不走代理）；聚宽=JS 空壳需无头浏览器（未解决）；付费研报 PDF 待人工

## 当前状态（2026-10-13 下午）
- **MTG004 已成会**：纪要 `70_meetings/MTG004_基线评审纪要.md`（§1-10），用户批准全部决议 + 转工程两事项 + HO003 交付路线；**重验证登记册（§10）8 项已执行 4 项**
- **DEC005 已批并三项全部闭环（2026-10-13 下午）**：
  ①RS015 reversal 方案 B（GT v2 锚定重测）**达标 31.6% ≥30% 线**（R-C hi，
  in/out 31.5/31.7%）→ tagger v2 门打开，但三 caveat 待裁决（LR 仅 1.06、
  hi 位触发 36.2% 大改占 TREND 位、规则与 GT leg1 定义亲和）——HO004-tagv2
  起草前须用户裁决；②RS015 range 方案 B2 **零晋升**（最优 out 21.0%），
  range 维持 v1 宽口径+门控降权，NR4 不实施；③RS016 RER 正式实验执行完毕
  **终止（G1/G3 FAIL）**：可交易口径 0/6 品种正、11/12 负年，臂间口径
  C>A>B 单调复现（环境效应真实、预注册机制收割不了）——**range_edge 闸门
  不放宽，HO004-RER 不开**
- **🔴 breakout 列勘误**：v1_acceptance"38.0%/LR 3.8×"系行列读位笔误，修正
  **31.8%/LR 1.15**（弱正信息）；A1/A3 结论不受影响；CAND-007 判读强度下调；
  勘误附录在 v1_acceptance.md（原文保留）；v1.1 协议下 reversal 结构规则
  全族无一过基率（RS015 §2.1-2.2）
- **HO003 已被工程侧实施交付**：ContextTaggerV1（两层 range/A2 反向位移/A3 双向迟滞）+ strict_range 列 + by_year 全档位；v1 验收完成（`assets/RS012/v1_acceptance.md`）：**A3✓**（breakout 中位 7 根、行为反转 B>A）/ **A1 部分**（触发 15.7%✓、判别力弱 LR1.09✗、两层结构×RER ✓）/ **A2✗**（reversal 15.7% 持平，列似然比 0.82 反向信息→编排禁用）
- **验证队列 7 项全闭环**（P1✅门控存疑降权 / P2✅弱支持不成立 / RS010✅ / H1L1⏳待 detector 独立评审 / W-M✅ / Alpha101✅ / M-LV-002✅）
- **optimizing 阶段**：W底（风险预算规则✓ 回测 +60%R 回撤减半，9/9 参数稳健）+ RER（**RS016 终局：strict_range 正式实验未过门，扩样方向关闭**）+ 突破族持仓管理（regime_exit F>R 已定：维持固定持有）
- **S-004 编排规则草案**（待 MTG 复核）：同窗反向冲突突破优先（54.2%，+968R 摆动）/ 同向合并
- **挖掘冻结令已解除**（基线=天然样本外）；新探索仍须基线外验证前置

## 关键实证边界地图（每格有档案，禁区=有失败实验背书）
| 方法/信号 | 有效范围 | 禁区 |
|---|---|---|
| mom6 突破段溢价 | **持仓期属性**（v1 迟滞后 B>A）| 入场时机✗（v0/v1 两次验证）|
| M-EX-003 absorption | 独立 60m 多头衰竭判据（浅调/上升回调最优 +0.119%）| 空头侧✗ 深跌✗ 他信号过滤叠加✗（两次失败）|
| M-TR-002 trend_score | 跨品种排序（S-004 优中选优）| 独立方向信号✗ |
| M-DV-001 量比背离 | **已撤销**（MTG004）| 反转判据永久✗（放量反弹=派发）|
| tick 规格分层 | 风险提示/监控维度 | 编排变量✗（P2 弱支持/不成立）|
| 明牌基准 | 及格线=扣费后为正 | 三族≈零毛边际（20 万笔）|
| RER 边缘反转 | strict_range 交集内 20 根收益口径为正且单调（+0.106%，C>A>B）| **T1=2R 可交易口径全负✗（RS016 终止：−0.29R，0/6 品种）**；裸形态✗（−0.036%，3.3 万笔）|
| 编排冲突 | 突破优先（54.2%）| 同窗反向听回调✗（−968R 摆动）|

## 文件地图
- `STATUS.md`：单页总览 + 最近动态 + 硬阻塞表 + 本胶囊引用
- `20_research/`：RS001-016（RS015 v2 议题+诊断结论 / RS016 RER 正式实验预注册；
  RS012 阶段判定 / RS013 阶段 IC+CAND-007 / RS014 量价双假说）
- `30_method_library/MLIB`：24 方法（M-DV-001 已撤销）+ 每方法边界状态行
- `40_candidates/`：10 张卡（001 拒绝 / 007 受限启用候选 / 008-009 采集预评完）
- `60_decisions/`：**HO004 final（reversal 退役+R-C 实装，用户批准 2026-10-13，待工程拾取）**/ HO003 final（已实施）/ HO002 / **DEC005（RS015-B/B2 与 RS016 执行批复）** / DEC002 / DELIVERY / DEC003（佣金=保证金×万3）
- `70_meetings/`：MTG004 纪要（§1-10 + 复验册）+ MTG004-PREP（判读草案+议程）
- `assets/`：RS012（GT+confusion+v1_acceptance 含勘误附录）/ **RS015（v2 候选诊断
  context_v2_diagnostic.md + GT v2 重测与 B2 屏幕 rev2_retest_and_range_screen.md
  + {sym}_gt_rev2_labels.csv）**/ **RS016（rer_formal.md 终局报告）**/ RS013（IC+cand007
  +regime_exit）/ MTG004（判读草案+overlap+tiebreak+风险预算+rer_expand+rer_robustness
  +各解剖）/ RS011（P2）/ BENCH / MLIB（各检验）/ CAND-001（h2h）/ CAND-009（strict_vs_loose）
- `code/analysis/`：28 脚本（本轮新增 context_v2_diagnostic.py / rer_formal.py /
  rs015_followup.py）；`code/methods/`：6 模块 36 函数/类；`code/tests/`：15 项

## 待办（依赖驱动，无自主空转项）
1. **HO004 已 final（用户批复"同意工程改造"），等工程拾取**：交付契约=
   `vnpy_patiming/output/baseline/context_tags_v2/`；研究侧验收 runner
   `ho004_acceptance.py` 已预置（等待态验证通过）→ 交付即跑 B1（GT v2
   ≥30%）/B2（GT 变体 ×4 均 ≥25%，失败回滚 A2 保留 A1）/B3（非退化）。
   range 线已闭环（B2 零晋升，无动作）
2. **H1/W 独立评审 PASS**（工程侧）→ H1/L1 切片实验 + W/M 扩样（验证队列+optimizing）
3. **用户侧**：§9c/§9d 新决议复核意见（不阻塞）；HO003 v1 复测结果知会工程对话
4. **季度**：重验证登记册（纪要 §10）逐项按触发条件执行

## 佣金与成本口径
- **DEC003（现行）**：佣金 = 保证金 × 万3 双边（0.0003×价×乘数×保证金率；RB .10/CU .10/AG .12/M .08/MA .09/TA .09）——基线与后续复算统一此口径
- 研究侧历史前瞻框架（RS013/RS014/h2h 等）旧口径为名义额万3——边际结论不变，数字复算时注意标注
