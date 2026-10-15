# 文档管理规范（Conventions）

## 0. 根部联保文档与生产策略登记

- **根部联保文档**（living，状态变化当轮同步）：`RESEARCH_HANDOFF.md`（交接胶囊+治理）、
  `STATUS.md`（管线总览）、`STRATEGY_TABLE.md`（策略台账）、`TEMPLATE_*.md`（固化框架模板）
- **生产在运策略**（quant-repo 仓，如 LinuxSignalScanner/市场选品扫描/RegimeSwitch）
  **不占用 S-XXX 序列**：以类名登记于 `STRATEGY_TABLE.md` "零"节；研究补课报告
  （20_research/RS-XXX）按类名引用；研究产出落地为生产选品策略时，才走
  S-XXX/CAND 立项流程
- 固化框架模板（TEMPLATE_*.md）：schema/边界冻结，变更走 HO（附《交付价值评估》）

## 1. 命名规则

### 策略主文档（一策略一文档）

- 目录：`10_strategies/`
- 统一格式：`{S-XXX}_{策略短名}.md`
- 策略短名：中文或小写英文，不含空格，用 `-` 连接；文件名不含日期（文档跨生命周期长期更新）
- 示例：`S-001_日内PA-突破.md`、`S-002_双均线.md`

### 其他文档

- 决策日志：`DEC{三位序号}_{主题}_{YYYYMMDD}.md`
- 会议纪要：`MTG{三位序号}_{主题}_{YYYYMMDD}.md`
- 附件：`assets/{S-XXX}/` 下按用途命名，如 `S-001_param-grid-20261012.png`

## 2. 策略 ID

- 每个策略立项即分配永久 ID：`S-XXX`（如 S-001），ID 即其主文档的身份标识
- 主文档贯穿全生命周期，ID 不变；决策日志、会议纪要、组合方案均按 ID 引用策略
- ID 只增不复用；被否决的策略其 ID 一并封存（文档移入 90_archive/）

## 3. 状态机

策略主文档头部 `status` 字段取值（生命周期状态）：

| 状态 | 含义 |
|------|------|
| draft | 想法阶段，逻辑草拟中 |
| researching | 研究中 |
| backtesting | 回测中 |
| optimizing | 参数优化中 |
| portfolio-candidate | 组合候选（通过优化评审） |
| live | 已纳入组合，跟踪中 |
| on-hold | 搁置（标注原因，保留在 10_strategies/） |
| rejected | 否决（文档移入 90_archive/） |

会议纪要与决策日志文档头部 `status` 仅用 draft / final 两值。

## 4. 文档头部元信息（统一 YAML 头）

策略主文档：

```yaml
---
id: S-001
name: 日内PA-突破
category: 日内PA
status: backtesting
created: 2026-10-12
updated: 2026-10-12
owner: RES
---
```

其他文档（决策/纪要）：

```yaml
---
id: DEC001 / MTG001
title: S-001 准入组合评审
status: final
created: 2026-10-12
related: [S-001, MTG003]
---
```

## 5. 版本与更新

- **主文档就地更新**：策略各阶段进展一律更新其主文档（`updated` 字段 +
  文末"修订记录"追加一行），不按阶段新开文档
- 多轮回测：更新 §5"回测记录"最新快照，历史轮次记入 §5.4"历史回测轮次"表
- 结论推翻先前结论：不删除旧内容，在修订记录中写明"推翻 §X 的 YY 结论"及理由
- 否决/终止的策略：主文档整体移入 `90_archive/`，文件名与 ID 不变

## 6. 会议纪要

- 每轮团队协商必须落纪要至 `70_meetings/`，命名 `MTG{序号}_{主题}_{日期}.md`
- 纪要中必须记录：出席角色、各方观点、分歧点、最终结论、待办（含移交工程侧的待办）

## 7. 索引维护

- 策略清单以 `10_strategies/` 目录文件名即索引；文件名须与文档头部 `id`/`name` 一致
- 跨文档检索通过策略 ID（S-XXX）与 `related` 字段完成
- 每次策略状态跨阶段变更时，同步更新决策日志
