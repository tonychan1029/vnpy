# 交接记忆胶囊 · AIPRJ 量化系统 v1.3.0(2026-10-12 晚)

> 本版为重大更新:策略框架三轮评审史 + 周二自动部署机制 + 全部待办。接手者请全文读完。
> 维护规则:每会话结束必须更新本文件;上下文不稳时以本文件 + 仓库 todo 为准,勿凭记忆。

## 环境
- **106 生产机**: `ssh tony@192.168.50.106`(tony 免密 sudo);本地代理 `192.168.50.106:7890`(GitHub 抖动时 git 加 `-c http.proxy=…`)
- **三仓(当前 head,工作区干净,全部已推送)**:
  - `D:\AIprj\quant-repo` main=**7290cee**(Phase A 全量实施:tf_selector 接线/组合策略基座与两具体类/影子 boot/排空脚本;selfcheck 74→77);**106 已部署并常驻影子跑**(trend_pullback RB0/CU0,1d,ShadowSink,日志 /home/tony/shadow_boot.log)
  - `D:\AIprj\vnpy` master=**(7e0abf6+62839f2)**HO001 基线+HO002 两 detector+DEC003/DEC004;**HO002 已于 04:06 部署 106**(默认关,11 detector 验证,preflight 6/6);基线产物 vnpy_patiming/output/baseline/ 未入库
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

## 2026-10-12 深夜工程会话(vnpy 工作区;交接胶囊维护)
- **HO001 基线交付**(7e0abf6):6 品种 51,696 草稿/122,404 context 行 → `vnpy_patiming/output/baseline/`
  (signals_detail/summary_by_signal_id/summary_by_year/baseline_report.md/context_tags/{prod}.csv);
  口径:三档成本 p0/p1/p2、**佣金=保证金×万3 双边(DEC003,用户深夜修订,名义额口径作废)**、
  T1=2R/同根双触保守 SL、horizon=40、in/out 仅打标签;判定侧 context v0 规则全文在报告
- **HO002 A1 实现完成,待独立评审**:PullbackOrdinalDetector(H1_L1_TREND)+WmDetector(W_BOTTOM/M_TOP)
  默认 cfg 关闭,注册零回归(runtime 同向抑制双顶底仅在 w_m 开启时生效);16 单测过;
  vnpy 工程套件 74 过+2 环境失败(redis/mcp e2e,存量)
- **Phase A 本地项**(718d7db):#13a/#13b/#2/#5 完成+壳生命周期桩测试补齐;
  **set_bindings staticmethod 修复**(类属性函数描述符会把 self 注入绑定回调——评审盲区自检抓到的真 bug);
  selfcheck 57→74;test_late_night_close_fires_at_0230 为存量失败(stash 验证),待查
- **错误提交处置**:QUANT_HANDOFF.md 从 Cloudflarewebhook 迁至 vnpy 根并入库;e7d1d7a 删除已推

## 2026-10-13 上午 Phase A 收官(用户授权解除窗口限制)
- **#10-12 接线**:两模型 exec_timeframe 经 tf_selector(atr_pct 指标;pool_config 新增
  scan.exec_tf_rules/default_exec_tf;指标缺失回落 monitor_tf)
- **#7 装包**:vnpy_portfoliostrategy==1.3.0(本地+106 venv;PyPI 无 4.4.0——胶囊旧表述
  "版本对齐 4.4.0"实指兼容 vnpy 核心 4.4.0,已核)
- **#1 具体策略类**:strategies/framework_base.py(组合基座:分品种 BarGenerator 字典/
  分品种水位与 prev_bucket/CloseAggregator 单次 replace)+两具体类;与 template.py 1.3.0
  逐条对齐(构造签名/update_setting 白名单/on_bars 切片/load_bars 预热)
- **#6+#3+#4**:services/framework_boot.py 影子跑(poll 切片合成 1m→on_bars;ShadowSink
  零生产影响;legacy PoolStore 快照喂 ShadowComparator;InstructionSink 真提交代码层
  PhaseBError 门禁,评审 PASS 前不可开);数据模式=poll(影子不依赖 CTP;Phase B 真订阅
  另接 OI 解析器)
- **#8 排空脚本化**:scripts/drain_legacy_instructions.py(plan 默认;apply 双门禁)
- **#7 附带**:poolscan 新版(含 #2 evaluate_product+tf_selector 接线)已部署 106 并重启
  runner——影子对比两侧同版本,无漂移
- **部署验证**:106 远端 selfcheck 77/77;影子常驻(PID 4089376,/home/tony/shadow_boot.log,
  首次评估节点=下一个 60m 收线);production runner/poolscan 重启后 active
- **影子跑观察**:**N=5 交易日(用户定,10-13~10-19;10-20 出差异清单提交用户确认=
  Phase B 门禁材料)**;进程已迁移 **systemd 常驻 quant-shadow.service**(enabled 自启+
  Restart=always,扛 5 日跨度的重启/崩溃);差异报告落
  /opt/aiprj/selection/.cache/shadow_compare/;第四轮评审进行中(子代理)
- **遗留清理(10-13 午前)**:test_late_night_close 存量失败=陈旧夹具(夜盘归属改为
  上一交易日后夹具未更新,补 9/29 归属日)已修,selection_runner 测试 11/11(ba34866);
  vnpy 两环境失败=纯环境——本地 Redis 6379 起服+PATIMING_STRATEGY_MCP_TOKEN_FILE
  (拉取 106 token 存 ~/.vntrader/)+PATIMING_MCP_URL 后 **76+2 全过(含真实 106 MCP
  e2e)**;远端 db.py(+2)/exit_ladder_eval.py(+56)漂移已对齐部署(引擎重启,preflight
  6/6);影子 legacy 池读取修正(entries_for_scanner,原误猜 load_entries 被静默吞)并带
  修复重启——15:00 节点起对比两侧数据齐全;**坑+1:pkill/pgrep -f 模式含路径会自匹配
  杀掉自己的 ssh 会话,用 [f] 正则技巧或分离命令**
- **cloudwebhook 缺信修复(10-13 午)**:用户报盘后选品未达 cloudwebhook——根因=106
  gateway_config `provider: hermes` 单通道,fanout 双路从未启用(CUSTOM_WEBHOOK_SECRET
  env 106 缺失);已切 `provider: fanout`(hermes 腿密钥走 ~/.hermes route;custom 密钥
  内联 640 配置,值=Worker README 记录的 1008991001),--test 双腿发送成功,15:05 盘后
  选品起双通道送达。**密钥卫生待办**:WEBHOOK_SECRET 明文见 Cloudflarewebhook README/
  HANDOFF,建议轮换并停止入库(需同步 Worker secret+Android local.properties)
- **第四轮评审启动(10-13 午)**:对话管线独立子代理评审员(与实施者隔离),范围=Phase A
  全量+历史 CLOSED/OPEN 核验+三点质疑权行使;报告将落 quant-repo
  reviews_v2/phase_a_round4_review.md(首份存档)。**时点注**:11:31 选品推送发生在
  11:46 fanout 切换前(仅 Hermes);首次真实双通道=15:05 盘后选品

## 2026-10-13 HO003 实施(context v1 修正+by_year 补导出)
- baseline_backtest.py:新增 ContextTaggerV1(HO003 A1 两层 range/A2 reversal 已实现
  反向位移/A3 breakout 双向迟滞)+--mode export-context / resummarize
- 交付:context_tags/{prod}.csv(**v1+strict_range 列**,122,404 行)+
  context_v1_acceptance.md(预检 **PASS**:range 15.7%≥8%,breakout 中位 7≥5,
  strict_range 2.1%)+summary_by_year 升 p0/p1/p2 全档位(B 项)
- **偏离标注**:A3 迟滞规格 2/2→实现 2/5(2/2 实测中位仅 3;exit=5 结构保证最短
  run≥5;研究侧 regime_retest 复核裁决)
- 已交付信号基线未重跑(v0 读数保护 MTG004 结论);正式验收=研究侧重跑
  rs012_confusion.py(经 tag_adapter)与 regime_retest.py

## Phase A 待办(设计稿 §3 行 1-13;完成后再送第四轮独立评审)
- [x] #10 15m 桶语义 / #11 1d 触发时效(60m 链路 15:00) / #12 tf_selector 模块+单测 / #13 部分(全败不推进/告警限频/规则预校验)
- [ ] #10-12 收尾: tf_selector 接线两模型+pool_config 键(poolscan 周二冻结,部署后接入)
- [x] #13 余项: 旧 id 排空查询按 legacy 精确形状(identity.is_legacy_instruction_id/select_legacy_ids)、文档统一 replace_scanner_entries 命名
- [ ] #1 具体策略类(portfolio 基类装包后对齐源码);[x] 壳生命周期离线测试(桩 vnpy BarGenerator)+set_bindings 修复
- [x] #2 trend_pullback 提取 evaluate_product(poolscan.py,行为保持,staging 随下一窗口)
- [ ] #3 InstructionSink 接线 boot(模块与校验已有;接线随 #6,依赖 #7)
- [ ] #4 影子对比器接线(ShadowComparator 已写;接线随 #6,依赖 #7)
- [x] #5 universe→settings 生成器(strategy_framework/universe.py,解析失败告警+跳过)
- [ ] #6 boot 集成(MainEngine+portfolio 引擎无头;依赖 #7 装包)
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
