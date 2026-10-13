---
id: HO004
title: context 标签 v2：reversal 旧规则退役与新定义（R-C）实装移交单
status: final（用户批准 2026-10-13："同意工程改造"；批准栏已签）
created: 2026-10-13
author: 研究团队（RES）
related: [RS015, DEC005, RS012, HO003, v1_acceptance, MTG004纪要§10, S-003, S-004]
---

# HO004：reversal 退役（旧语义）+ 实装（v2 R-C 定义）

> 依据链：HO003 v1 验收 A2✗（reversal 列 15.7%、LR 0.82 反向信息）→
> RS015 离线诊断（v1.1 协议下结构规则全族无一过基率）→ 用户批复方案 B
> （GT v2 锚定重测，DEC005）→ 重测达标 31.6% ≥30% 线（RS015 §2.4）→
> 用户批复"同意退役和实装"（2026-10-13）。
> **语义澄清（批复的解释，批准栏签署即确认）**：退役对象是 v0/v1 的
> 「EMA 斜率×(close−EMA20) 异号（±5 根反向位移）」规则及其"阶段怀疑"
> 语义；实装对象是 RS015 §2.4 达标的 R-C 定义（已实现结构破坏：先行腿+
> 反向位移+回撤 50%），以 `reversal` 同名标签接管。词表字符串不变，
> 含义整体替换。

## 零交易风险声明

context_tag 为判定侧仪表（信号与编排当前不消费 reversal——编排侧自
v1 验收起已禁用）。本单改动不触碰任何交易行为、信号生成与基线回测
数值；工程工作量仅为 tagger 分支逻辑与导出词表。

## A. 判定侧改造（工程）

### A1. 退役旧 reversal 规则
- 删除现行分支：`slope × (close−EMA20) < 0 且 5 根反向位移 ≥1×ATR`
  （ContextTaggerV1 的 reversal 位，含其 v0 前身语义）；
- 词表说明：`reversal` 字符串保留但含义整体替换为 A2 的新定义；
  `baseline_report`/导出自检中的词表说明同步更新。

### A2. 实装新 reversal（R-C，参数固定如下）
- 条件（全部 as-of 可算，只需 closes + ATR，无摆动点依赖）：
  1. **先行腿**：近 20 根 close 极值（含当前根）相对其前溯 40 根窗内
     基点的幅度 ≥ **2.0×ATR**（上行/下行对称取或）；
  2. **已实现反向位移**：当前 close 自该极值回撤 ≥ **1.0×ATR**；
  3. **回撤比例**：回撤 / 先行腿 ≥ **0.5**；
- **占位**：breakout（迟滞不变）→ range（宽口径不变）→ **reversal(v2)**
  → trend_strong/trend_channel → 兜底。即新 reversal 提到 trend 分支
  之前（RS015 达标变体即此占位；旧 reversal 位在 trend 之后）；
- strict_range 子态列定义**原样不动**；breakout 迟滞（enter2/exit5）
  **不动**；其余分支条件不动。

### A3. 导出与格式
- context_tags CSV 列不变（datetime, symbol, context_tag, strict_range）；
- **交付路径：`vnpy_patiming/output/baseline/context_tags_v2/`（新目录，
  6 品种 `{SYM}_context_tags.csv`）——v1 目录 `context_tags/` 原样保留，
  供 B3 非退化对照**；
- `reversal` 触发占比预期 ~36%（RS015 实测 36.2%），远高于旧语义 6%——
  导出自检的合理性区间请按新值更新。

## B. 验收（预注册，研究侧执行，交付=脚本重跑，工程无需另写）

- **B1 主验收**：GT v2 协议（研究侧已交付
  `assets/RS015/{sym}_gt_rev2_labels.csv`，锚定第一腿定义见
  rs015_followup.py 头注）下重跑混淆矩阵——reversal 列精确率 **≥30%**
  且 LR ≥1.0（不复现反向信息）；
- **B2 敏感性（回应"定义亲和"caveat）**：GT v2 变体矩阵（leg 回看窗
  40↔20、阈值 1.5↔2.0 共 4 组合）下 reversal 列精确率均 ≥25%——
  证明达标非定义重叠伪影；
- **B3 非退化**：GT v1.1 口径下 RANGE 列精确率与触发占比不劣化
  （结构性保证：新分支在 range 之后，不与 range 抢点）；BREAKOUT 列
  v1.1 口径不劣化；trend 类 top-pred 变化仅记录（新分支会从 trend
  处分走 ~1/3 时点，属设计行为）；
- **B4 词表/消费方迁移**：S-003 DOUBLE_TOP_BOTTOM 背景
  `{range, reversal}` → **`{range}`**（v2 reversal 语义=往返中段，
  ≠区间环境；DT 已否决、DB 在 optimizing 不受影响）；wedge 已归档
  无动作；**S-004 维持不消费 reversal**（36% 触发占比不具备过滤价值，
  消费者研究另立项）；
- 验收脚本：研究侧 `rs012_confusion.py`（GT v2 与 v1.1 各跑一遍）+
  B2 变体脚本（研究侧新增）。

## C. 研究侧并行项（非工程依赖）

- context_eval 协议文件补 GT v2 函数并标注 v1.1/v2 并存（研究侧）；
- RS012 修订记录登记协议切换；重验证登记册（MTG004 §10）增补行：
  "reversal v2 决议 → 触发=v2 标签交付后复跑全套判定侧口径"。

## D. 已知边界与风险（如实呈现）

1. LR 仅 1.06（v2 基率 29.8%）：新标签是**弱信息**——实装目的为研究
   仪表与未来消费方研究，不承诺编排增益；
2. 触发占比 36%：标签较"胖"，任何把它当稀疏事件的用法都不成立；
3. 30% 线为绝对精确率口径，已含 B2 敏感性护栏；若 B2 失败按验收不通过
   处理（回滚 A2，保留 A1 退役）。

## 用户批准栏

- [x] 批准 A1/A2/A3 + B 全部（B4 消费方改挂含 S-003 一处）
  ——**用户批复"同意工程改造"（2026-10-13），本单转 final**
