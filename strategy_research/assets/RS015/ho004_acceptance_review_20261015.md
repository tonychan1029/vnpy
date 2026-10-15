# HO004 验收复核（研究侧，2026-10-15）

> 载体链：工程交付 `vnpy_patiming/output/baseline/context_tags_v2/`（2026-10-14
> 22:27）+ 工程自检预检 PASS（context_v2_acceptance.md，2026-10-15 14:38）→
> 研究侧正式验收 runner（ho004_acceptance.py，B1/B2/B3 预注册机械判读）→
> 本复核。

## 1. 机械验收结果（ho004_acceptance.md，2026-10-15）

| 门 | 结果 | 关键数字 |
|---|---|---|
| B1 主验收（GT v2） | ✅ PASS | reversal 精确率 32.7%（≥30%），LR 1.06（≥1.0），触发占比 34.8% |
| B2 敏感性（GT v2 变体×4） | ✅ PASS | 32.7% / 32.2% / 29.4% / 27.3%，均 ≥25% |
| B3 非退化（GT v1.1） | ⚠️ 机械 FAIL（边界伪影，见 §2） | v2 与 v1 锚逐位一致：RANGE 19.0%（触发 17.0%）、BREAKOUT 31.8%（精确 0.317684） |

## 2. B3 机械 FAIL 的边界诊断（ho004_b3_boundary_diag.py → ho004_b3_boundary_diag.md）

**诊断结论：B3 FAIL 系阈值校准伪影，非退化实质成立。** 三条证据：

1. **锚自检不过线**：预注册阈值 ≥31.8% 取自历史报告的四舍五入显示值；
   BREAKOUT 精确率的精确值 = **0.317684**，v1 tags 锚自己也不满足 `≥0.318`
   ——阈值按舍入值设定所致；
2. **v2 与锚逐位一致**：RANGE 0.190052/触发 0.169945、BREAKOUT 0.317684/
   触发 0.200052，v2 与 v1 锚完全相同——非退化的设计意图（"tag 集合结构性
   应逐点一致"）在 RANGE/BREAKOUT 列精确达成；
3. **差分仅占位迁移**：19,165 对可比点中 6,681 点差异，全部为
   trend_strong→reversal（4,909）/ trend_channel→reversal（1,154）/
   reversal→trend_channel（618）——正是 A2（R-C v2 提前至 trend 分支前）的
   设计行为，RANGE/BREAKOUT 零扰动。

## 3. 研究侧判读与处置建议

- **研究侧判读**：B1/B2 通过；B3 非退化实质成立（机械 FAIL 为阈值校准
  伪影）。HO004 三门验收**实质通过**。
- **⚠️ 用户裁决（2026-10-15）：选 A——B3 非退化实质通过，HO004 验收通过落档**；
  教训登记入治理（RESEARCH_HANDOFF 治理节）："预注册验收阈值禁止取自舍入
  显示值，必须以精确值落档；验收 runner 内置锚自检"。
- **生产现状（106 SSH 只读核实，2026-10-15）**：HO004+HO005 已于 2026-10-14
  22:25 经用户授权提前窗口部署（journalctl：stage verified→installed→
  restarted ok→selfcheck ok→preflight 6/6→DEPLOY_OK）；四服务 active；
  poolscan.py 含 rollover/contract_code 标记；`market_min_rr` 仍 1.0
  （R10 随 HO006 批次 2026-10-16 04:15 部署）。
- HO005 验收状态：部署✅ + 预检✅；正式单测/集成记录待工程侧归档；
  最终验证=下次真实换月生产观察（研究侧复核）。

## 4. 教训登记（建议纳入治理）

- 预注册验收阈值必须以**精确值**落档（保留 6 位小数），不得引用报告中的
  舍入显示值——B3 本轮即因此产生假 FAIL；
- 验收 runner 应内置"锚自检"（对照臂同样跑阈值），锚不过线即自动标记
  阈值校准问题，避免人工误读。
