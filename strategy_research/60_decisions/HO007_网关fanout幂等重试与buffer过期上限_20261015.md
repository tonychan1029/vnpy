---
id: HO007
title: 网关 fanout 幂等重试、批次上限与 buffer 时效复检（通知通道风暴加固）
status: 实施完成待独立评审（用户 2026-10-15 令：完成即启动评审，评审通过及时部署）
created: 2026-10-15
author: DSH 工程会话（依据 2026-10-15 晨通道故障复盘）
related: [QUANT_HANDOFF, HO005, HO006]
---

# HO007：网关 fanout 幂等重试、批次上限与 buffer 时效复检

> 背景：2026-10-15 00:55-08:22 custom 腿 401 造成 **5.5 小时、5181 轮无界重试**，
> 同一条 02:30 的 CU0 选品在微信被重复投递（标题时间戳每轮重渲染），且该信号卡在内存
> buffer 里绕过了 30s 过期闸门（通道恢复后差点在开盘前补推一条 5.5 小时前的裸信号）。
> 故障由 secret 失配引起，**已按用户令修复**（见 QUANT_HANDOFF 同段）；本单处理
> **放大器**（批次语义）与**闸门下沉**，与 secret 无关。

## 交付价值评估（治理必备）

| 维度 | 内容 |
|---|---|
| 预期收益 | ① 单腿故障不再污染健康通道（本次 5181 轮 → ≤1 条）；② 批次有上限，不再永久占用 buffer 并阻塞后续新信号；③ 发送前复检时效，杜绝"开盘后补推陈旧裸信号"；④ **修复 D1 静默丢通知**（见下：原实现每进程生命周期内**只有首个成功批次真正投递**，其后每批都零请求却记"已推送"） |
| 工程成本 | **低**：单文件 `services/webhook_gateway.py`（`FanoutSender` + `gateway_loop` + 两个纯函数），新增 7 个单测/断言；无 schema/协议变更 |
| 不交付的代价 | 下次任一通道故障即重演风暴；且 D1 使"已推送"日志不可信——通知实际是否送达无法从日志判断（观测性缺陷） |
| 替代方案 | 仅加通道熔断——治标：仍会重复一次并把批次留 pending；不推荐单独交付 |
| 下行风险 | 有界——纯通知层、无交易行为；回滚=还原 `.bak_ho007_20261015` + 重启 quant-webhook（无状态） |

## A. 改动清单（services/webhook_gateway.py）

- **A1 幂等 fanout**：`FanoutSender.__call__` 只把**本轮失败**的 target 留 pending，成功腿本轮
  出清（原实现"部分失败保留全部 pending"→ 健康通道被无界重复投递）。
- **A2 批次上限**：`gateway_loop` 增 `max_attempts`（默认 5）与 `batch_deadline`（默认 120s），
  超限丢弃批次 + `logger.error` 计数；`poll_interval`/`retry_backoff` 可注入（测试用）。
- **A3 时效复检下沉**：新增 `_partition_fresh()`，发送前按 `max_staleness` 复检 buffer
  内每条信号（timestamp 缺失/非法放行，与出队闸门同宽容度）。
- **D1 批次完成语义（实现期间发现的存量缺陷）**：原实现在批次全成功后 `self.pending.clear()`，
  而 `pending` 仅在 `__init__` 播种 → **之后每个批次都是空批次**（`asyncio.gather()` 零任务不抛错），
  `gateway_loop` 仍打印"已推送 N 条合并信号" → 进程内首个成功批次后**静默丢通知**。
  修复：`FanoutSender.start_batch()` 显式开批次（`gateway_loop` 在批次开始时经 `_begin_batch()`
  调用），`__call__` 另加"空 pending ⇒ 按新批次处理"的防御兜底，任何调用路径都不会零请求报成功。
- **未做（保留待议）**：A4 通道级熔断（连续失败→该腿降级/暂停）；本次以 A1+A2 已消除风暴。

## B. 验收方式（已执行）

1. 单测（`tests/test_webhook_gateway.py`，pytest）：`12 passed`
   - A1：健康腿只投 1 次、重试只打失败腿（`pending == {"custom"}`）；
   - D1：批次完成后开新批次仍覆盖全部目标（含忘调 `start_batch` 的防御路径）；
   - A3：`_partition_fresh` 丢弃过期/边界（age==max_staleness）保留新鲜与缺失 timestamp；
   - A2：`gateway_loop` 在 `max_attempts` 后放弃批次（断言尝试次数恰为 2）；
   - A2+D1：被放弃批次不补投，其后的新信号正常投递。
2. 集成脚本（`tests/test_fanout_gateway.py`，真实本地 HTTP 双通道）：`[PASS]`
   - 首轮 hermes 503/custom 200 → custom **恰好 1 次**（A1 无重复）；重试只打 hermes；
     显式开新批次后两腿各再 1 次（D1）。
3. 回归：`tests/test_patiming_webhook.py`、`tests/test_market_scan_webhook.py` 同批 `15 passed`；
   调用签名向后兼容（`tests/test_flow.py`、`tests/test_gateway_live.py` 位置/关键字参数不变）。

## C. 部署（用户令：评审通过及时部署）

- 落地：`services/webhook_gateway.py` → `/opt/aiprj/services/webhook_gateway.py`（原样字节，LF）；
  守卫式脚本 `deploy/ho007_gateway_deploy_20261015.sh`（stage md5 → 备份 → 安装+md5 复核 →
  重启 → **PID 级** Traceback/正向启动断言 → smoke → 标记），用户授权窗口外 `--force-now`。
- 回滚：`.bak_ho007_20261015` + `systemctl restart quant-webhook`（脚本内自动回滚同）。
- 部署后核验：①md5 一致；②服务 active + "防抖网关启动"行无 Traceback；③**D1 生产实证**：
  间隔注入 2 条 TEST → 应产生 2 次真实投递（旧实现第 2 批为幻影）；④下一扫描节点（10:16）
  双通道同文到达、无重复。

## C2. 独立评审与整改（2026-10-15）

- **一轮独立评审（只读子代理）：PASS-WITH-FINDINGS**，2 MAJOR + 4 MINOR + 2 NIT。
  关键确认：**D1 属真实存量缺陷**（对 HEAD 版实证：首个成功批次后，后续批次零请求却记
  "已推送 N 条合并信号"；新测试对 HEAD 版 = 6 failed / 7 passed）。
- **MAJOR-1（已整改）**：重试期间到达的新信号被并入在途批次 → 只发 pending 腿 → 健康腿漏发该信号
  （对 HEAD 是"重复"，对整改版一度变成"静默丢失"）。
- **MAJOR-2（已整改）**：批次被 A2 放弃时，连"从未尝试过任何腿"的新信号一起丢弃。
- **整改实现**：新增 `pending_new` 暂存 + `_start_next_batch()`——在途批次重试期间到达的新信号
  不并入、不丢弃；批次一解决（成功/放弃/被 A3 清空）即提升为新批次并重新武装全部目标。
  两处新增强回归测试，对"整改前"模拟版本实测 **FAIL**（非空转证明）。
- **MINOR 整改**：③成功日志追加 `目标=hermes,custom`（"已推送"可核对）；④`blocked` 在放弃/清空
  路径冲刷，不再错记到后续批次；⑤出队闸门与发送前复检共用 `_signal_age/_is_stale` 判据
  （缺失/非法 timestamp 一律放行，不再 KeyError；不再 int 截断）；⑥`--test --provider custom|feishu|hermes`
  因 `targets` 未绑定的存量 UnboundLocalError 顺带修（并加测试）。
- **留待后续（不影响本次部署）**：finding 7 陈旧脚本测试（`tests/test_flow.py` 的 `fake_send`
  签名、`tests/test_gateway_live.py` 的 `send_to_hermes` 直传 + Windows 路径断言——两者均已按
  评审建议修正，但后者仍需本地 redis + `services/gateway_config.yaml` 方可执行，本机未验）；
  finding 8 余项（默认参数下 `batch_deadline` 不易触发——已在 docstring 说明"取先到者"）；
  finding 9 nit（`send_to_provider(fanout)` 每次新建 sender）。
- **二轮独立验证（delta）**：见下（结论待补/已补）。

## C3. round-2 评审 MAJOR 与整改（2026-10-15 上午）

- **round-2 MAJOR（评审实证，探针 20 信号丢 13）**：`pending_new` 分支刷新了防抖时钟
  （`last_signal_time`），而在途批次的重试恰由该时钟放行 → 新到信号快于 window 时重试被
  无限拖延；被拖延的信号最终提升时又被 A3 判过期整批丢弃 → **健康腿静默丢新信号**。
- **整改（三项，均按评审建议）**：
  ① 重试与合并解耦：`pending_new` 分支不再触碰 `last_signal_time`（重试节奏由失败路径的
    `retry_backoff` 睡眠保证）；
  ② 合并等待设上限：自首批入缓冲起 `window` 亦触发发送（连续快流不再让批次饥饿）；
  ③ 重试预算 ⊆ 时效预算：`attempt_budget = min(max_attempts, max_staleness // retry_backoff)`，
    保证批次在暂存信号老化之前解决。
- **回归测试**：`test_fast_stream_during_outage_loses_no_signal`（快流 + 死腿 + 紧时效，
  断言每条信号恰好到达健康腿一次）——对"整改前"模拟版 **FAIL**（复现整批老化丢弃），
  对整改版 PASS；非空转证明。
- 其余：`dropped` 累计值并入三条丢弃日志（NIT-2 关闭）；放弃日志附符号清单
  （MINOR-3 关闭）；陈旧脚本测试两处已修（finding 7，其中 live 测试仍需环境才能跑）。

## D. 批准栏

- [x] 用户 2026-10-15 指令："修改完成需要启动评审，评审结束通过要及时部署"
- [x] 一轮独立评审 PASS-WITH-FINDINGS（MAJOR 全部整改 + 回归测试钉死）
- [x] 二轮独立复核：确认一轮 MAJOR 已修，另发现 round-2 MAJOR（重试拖延+A3 老化）
- [x] 三轮独立复核（delta，pinned `8eb7fd4f`）：PASS-WITH-FINDINGS，**MAJOR-CLOSED=YES**，
      变异验证非空转（回退三项整改 → 新测试 FAIL、整批老化丢弃复现）；60 信号快流+死腿
      探针 **60/60 恰好一次、0 重复、最大延迟 0.42s**；DEPLOY: YES。遗留 INFO（非回归）：
      F1 at-least-once 语义（接收端按 signal_id 去重可消）；F2 进程崩溃丢内存批次
      （需 ack 队列，超范围）；F3 NOTE 预算钳制分支未被该测试单独覆盖（防御性）。
- [x] **已部署**：2026-10-15 10:13 守卫式 `--force-now`（用户令"及时部署"，窗口外授权），
      **DEPLOY_OK** `gw_md5=8eb7fd4f`；smoke 两批次双通道全达——旧代码下第二批为幻影，
      即 **D1 修复的生产实证**；quant-repo=97a4896。部署后核验：三服务 active、
      0 Traceback、队列空、`已推送 … 目标=custom,hermes` 审计后缀生效。
