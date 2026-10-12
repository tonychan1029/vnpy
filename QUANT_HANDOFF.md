# 交接记忆胶囊 · AIPRJ 量化系统 v1.3.0(2026-10-12 晚)

> 本版为重大更新:策略框架三轮评审史 + 周二自动部署机制 + 全部待办。接手者请全文读完。
> 维护规则:每会话结束必须更新本文件;上下文不稳时以本文件 + 仓库 todo 为准,勿凭记忆。

## 环境
- **106 生产机**: `ssh tony@192.168.50.106`(tony 免密 sudo);本地代理 `192.168.50.106:7890`(GitHub 抖动时 git 加 `-c http.proxy=…`)
- **三仓(当前 head,工作区干净,全部已推送)**:
  - `D:\AIprj\quant-repo` main=**37c0acb**(本会话 8 提交:晚盘修复/日线波段/通知周期/框架骨架与 v2.1/部署脚本)
  - `D:\AIprj\vnpy` master=**407842c**(tracked 无改动;本胶囊迁至该仓根目录,未入库)
  - `D:\AIprj\Cloudflarewebhook` main=**e7d1d7a**(胶囊已删除迁移,历史仍含本文件)
- **106 部署布局**: `/opt/aiprj/selection|services|research/alpha_lab|sync_service|vnpy_patiming|venv`、`/opt/aiprj/cache`、`/home/tony/.hermes/`
- **⚠️ 本地工具坑(实测)**: pwsh 无 git(PATH)→用 `C:\Program Files\Git\cmd\git.exe`;pwsh→ssh 传参**内层双引号会被吞**(内层一律单引号;复杂脚本 `base64 -d | bash`);捆绑 Python 无 matplotlib、无 git;**loguru 默认 sink 是 DEBUG 级**——降 debug 不减 journald 量,要节流;PowerShell 单行命令里 `$` 会被展开

## 生产服务矩阵(全 active)
patiming-engine(8801 MCP) / selection-runner / quant-webhook / patiming-webhook / quant-mcp(8800) / hermes-gateway(8644) / redis 6381 / vnpy-sync.timer(01:05·02:40·10:16·11:31·15:05·17:35·23:05) / research-webui(:8889) / jupyterlab(:8888, token=patiming-research) / tradereplay(:8000) / **quant-pattern.service**(v1.2.3 未列,已补) / cron 12:00 holiday_gate_check(脚本 /opt/aiprj/selection/services/)

## 周二 2026-10-13 04:05 自动部署(已批准,勿动)
- **机制**: `/etc/cron.d/selection-deploy-20261013` → `/usr/local/sbin/selection-deploy-20261013.sh`(仓库 deploy/selection_deploy_20261013.sh 同源)。守卫:日期(仅 10-13)+DEPLOYED 标记+flock+小时窗(04)+md5 四把锁;poolscan 先装;任一门槛失败自动回滚;日志 `journalctl -t selection-deploy`。**窗口外手工试跑=安全 NO-OP(不删 cron)**
- **内容**: 晚盘两层缺陷修复(微秒相等→120s 窗口;`now.date()`→上一自然日夜盘口径)+启动补扫(30 分钟回看+`.cache/selection_runner_state.json` 水位)+日志节流(stale 10 分钟心跳/faulthandler 3600s)+**日线波段 trend_pullback 每日 15:00 节点**+选品通知周期修复(interval 取 selection_timeframe,不再恒 5m)+gate-check 增 late_night_fires+hermes 重启吸收环境
- **stage**: `/home/tony/selection_stage_20261011/` md5 锁定 runner=716aa3d4… poolscan=45bd7c6d… tests=18d88785…(旧版恰 28 例) gate=ed4b3c35…。**框架包不在其中(独立评审 PASS 前禁止 staged)**
- **核验**: 周二 09:30 提醒已挂;周三 09:30 双核验(晚盘首触+日线波段首跑)已挂

## 本会话发现并处置的问题
1. **晚盘补跑从未触发**(两层缺陷:微秒级精确相等+自然日闸门)→ 已修;首次真实触发=周三 10-14 凌晨 01:00/02:30
2. **周日 04:00 窗口会话未唤醒,部署错过** → 根治:部署下沉服务器 cron,桌面会话不参与生产操作
3. **hermes**:GLM_API_KEY 实为非空(49 字符,/etc/environment),"empty"报警是**进程环境陈旧**(服务先于 key 写入启动)→ 周二窗口重启吸收;**iLink 会话失效中(10-12 09:21 投递失败),用户须给 bot 发消息恢复**;DeepSeek 备用已配(config.yaml deepseek provider+fallback;DEEPSEEK_API_KEY/BASE_URL/MODELS 三件在 /etc/environment),待重启生效
4. **晨间网络抖动**(06:01 前后 httpx 断连,engine quote_poller+runner 同报,自愈;疑链路晨间重拨)——记录观察,暂不处理
5. 择时通知语义(用户定调):通知=信号+阶段序列提示(H1→H2;W 形态=左肩→等右肩),**主动权在用户,不代客下单/不给价格数量级参数**

## 策略框架(三轮评审史;当前=设计 v2.1+骨架,**未 staged**)
- **架构(用户定调)**: 组合品种基类 `vnpy_portfoliostrategy.StrategyTemplate`;一实例=模型×周期×品种域;输入=品种列表(**默认 universe:all 全市场**,可 list+products)+decision_tf+模型参数,命名 `{scanner}_{symbol|ALL}_{tf}`;输出三要素=品种+**择时周期(扫描策略量化选择,tf_selector,初始阈值占位待影子校准)**+信号列表(必填非空);扫描与择时只以数据 IO 耦合;契约冻结(timing_instruction schema/MCP/通知 payload)
- **三轮评审**: v1 FAIL(2B+11M+7m)→v2(b2a7bc9)→二审 架构 FAIL+安全 P-W-F(N1 tick 链路死路、N2 close_key 误报已裁定)→v2.1(2415ce5+dc50785+37c0acb+a6edd13)→**三审 PASS-WITH-FINDINGS,批准进入 Phase A**(评审员 ec777f41;portfolio 选型获背书,三点质疑权已并入门清单)
- **已落地模块**(services/strategy_framework/,自检 57/57=28 legacy+29 框架): settings(universe 契约)/identity v2(溢出 raise+exchange)/sink(Shadow/Composite failed 列表/CloseAggregator)/close_semantics(会话收线三分支+夜尾+不完整窗丢弃+水位)/selection_strategy(壳:update_setting 快照+parameters、TF_SPEC daily_end、trading 门、逐评估异常隔离、全 sink 失败不推进水位、bg 缺失限频告警、1d 由 60m 链路 15:00 触发)/tf_selector(规则阈值)/contracts(resolve_candidates 适配)/instruction_sink(v2 盖章+信号非空)/shadow_compare(小时桶归一)
- **流程教训**: 评审任务书不得预设选型边界——附"策略族选型质疑权";选型先列机制清单(ctastrategy/portfoliostrategy/scripttrader/自建)写 ADR;自检盲区=壳层生命周期(桩 vnpy BarGenerator 待补)

## Phase A 待办(设计稿 §3 行 1-13;完成后再送第四轮独立评审)
- [x] #10 15m 桶语义 / #11 1d 触发时效(60m 链路 15:00) / #12 tf_selector 模块+单测 / #13 部分(全败不推进/告警限频/规则预校验)
- [ ] #10-12 收尾: tf_selector 接线两模型+pool_config 键(poolscan 周二冻结,部署后接入)
- [ ] #13 余项: 旧 id 排空查询按 legacy 精确形状、文档统一 replace_scanner_entries 命名
- [ ] #1 具体策略类(portfolio 基类装包后对齐源码;**壳生命周期离线测试**=桩 vnpy BarGenerator,评审点名盲区)
- [ ] #2 trend_pullback 提取 evaluate_product(本地改,staging 随下一窗口)
- [ ] #3 InstructionSink 接线 boot(payload_builder=entry_to_instruction 适配)
- [ ] #4 影子对比器接线(ShadowComparator 已写,待接)
- [ ] #5 universe→settings 生成器(contracts+poolscan _discover_universe)
- [ ] #6 boot 集成(MainEngine+portfolio 引擎无头)
- [ ] #7 venv 安装 vnpy_portfoliostrategy(窗口内 pip 走代理,版本对齐 4.4.0)
- [ ] #8 旧 id 指令排空执行(legacy 精确形状过滤)
- [ ] #9 通知模板(引擎侧,Phase C)
- **门**: Phase A 完成自检→第四轮独立评审→PASS→影子跑(ShadowSink,≥N 交易日)→差异清单用户确认→Phase B 切换(旧 runner .bak+cron 回滚)→质量跟踪(胜率/RR 达成/出场复盘)→二期择时归化→退役旧池引擎

## 验证速查
```bash
ssh tony@192.168.50.106
journalctl -t selection-deploy --since '2026-10-13 04:00'   # 周二部署日志
journalctl -u selection-runner --since today | grep -E 'session close|daily swing|late-night|submitted'
sudo -n journalctl -t holiday-gate-check --since today
sudo -n -u aiprj env HOME=/opt/aiprj bash -c 'set -a; source /etc/aiprj/patiming.env; set +a; /opt/aiprj/venv/bin/python -m vnpy_patiming.preflight'  # 6/6 PASS
PYTHONPATH=/opt/aiprj/selection:/opt/aiprj /opt/aiprj/venv/bin/python /opt/aiprj/selection/tests/selfcheck_selection_gaps.py
```
本地自检: `$env:SEL_SELFCHECK_STUBS='C:\Users\16863\AppData\Local\Temp\sel_stubs'; & '<捆绑python>' D:\AIprj\quant-repo\tests\selfcheck_selection_gaps.py`(57/57;**⚠️ 桩目录在 %TEMP%,可能被清理,丢失则按胶囊重建 4 个桩文件**)

## 用户偏好/纪律(累计)
UI 界面优先,拒绝 SSH 日常使用;升级/重启只允许凌晨 04:00-05:15 窗口;决策类先问再做;单套 vnpy 不分叉,不重复造轮子;研究回测盘后跑与生产零耦合;**实施完成必须独立评审,通过才能提交部署**;流程图/设计稿先审后做;上下文不稳时以本胶囊+todo 为准,勿凭记忆。
