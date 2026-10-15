# 交接记忆胶囊 · AIPRJ 量化系统 v1.3.0(2026-10-12 晚)

> 本版为重大更新:策略框架三轮评审史 + 周二自动部署机制 + 全部待办。接手者请全文读完。
> 维护规则:每会话结束必须更新本文件;上下文不稳时以本文件 + 仓库 todo 为准,勿凭记忆。

## 环境
- **106 生产机**: `ssh tony@192.168.50.106`(tony 免密 sudo);本地代理 `192.168.50.106:7890`(GitHub 抖动时 git 加 `-c http.proxy=…`)
- **三仓(当前 head,工作区干净,全部已推送)**:
  - `D:\AIprj\quant-repo` main=**c81696c**(Phase A 全量+第四/五/六轮评审闭环+影子
    systemd 常驻+位阶闸门;106 已同步,远端 selfcheck 82/82)
  - `D:\AIprj\vnpy` master=**(7e0abf6…本文件提交)**HO001 基线+HO002 两 detector
    (已部署 106,默认关)+DEC003/004+HO003 ContextTaggerV1(v1 验收: A3✓/A1 部分✓/
    A2✗ reversal 编排禁用)+strategy_research 全量入库(研究侧 RESEARCH_HANDOFF.md
    为对位胶囊);基线产物 vnpy_patiming/output/baseline/ 未入库
  - `D:\AIprj\Cloudflarewebhook` main=**e662ac7**(胶囊迁出+WEBHOOK_SECRET 明文脱敏;
    **remote 内嵌凭据已剥离**,git 推送改走凭据管理器)
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
- **PAT 泄露处置闭环(10-13 午)**:API scope 回显定位泄露枚=classic `codex`(正在使用
  的工作凭据);处置=用户发新 fine-grained token(三仓 Contents+Workflows RW,90 天)
  → 凭据管理器更新 → 三仓推送认证实测全过;Cloudflarewebhook remote 内嵌凭据段已剥离;
  旧三枚(codex/codex2/aicoder)用户网页删除;**新惯例:git 推送一律走凭据管理器,
  remote/env 不再存 token 明文**。**实证闭环(10-13 12:0x)**:泄露值重打 API 返回
  401(已死亡),本条遗留彻底关闭
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

## 2026-10-13 第四轮 FAIL → 整改 → 第五轮 FAIL(5B-1) → 修复 → **第六轮 PASS** → 影子重启
- **第四轮独立评审判定 FAIL**(1 BLOCKER+4 MAJOR+7 MINOR+历史 OPEN 1;报告
  reviews_v2/phase_a_round4_review.md;历史 16 项 15 CLOSED——骨架与安全设计扎实,
  FAIL 限于本轮影子 boot 编排与组合基座失败路径):4B-1 影子只喂首实例(BLOCKER,
  CU0+ 框架侧零记录,N=5 证据失效)/4B-2 类级 sink 重绑定错标/4B-3 对比器退化为
  状态-vs-事件重灌/4B-4 flush 重试键型混淆+水位先行/4B-5 trend_pullback tf 接线
  死代码;**影子 quant-shadow 已按评审建议暂停**
- **整改完成**(ead7e91,全量验证绿:selfcheck 80/80、网关三脚本、回归 12 例):
  4B-1 逐实例喂条/4B-2 sink 实例级/4B-3 对比器事件化+有界(每 close 节点一份
  报告,4 项未归一化节点差 meta 标注)/4B-4 重试键=close_key+水位 commit-on-flush
  (+3 个失败路径用例)/4B-5 一行修/MINOR 批(4B-6 门禁 exchange/4B-7 断言更新+
  回归口径文档化/4B-8 交易所反查/4B-9 首启水位=boot/4B-10 cfg 透传/4B-11 drain
  REVOKED+PENDING_APPROVAL/4B-12 拒多产品 list)/H14 SKIP 单独计数
- **106 已同步修复版**(远端 selfcheck 80/80);**第五轮复审结论 FAIL(唯一项
  5B-1 MAJOR):4B-9 整改是死代码**——boot 绑实例属性,基座经 type(self) 类级
  查找落 None → 首启陈旧评估未消+水位持久化静默丢失(较 165315c 回归);
  **已修**(f0d75c3:两处 type(self)→self + 5N-1 告警实例优先 + 5N-2 死导入
  + 5N-3 boot 形态自检用例×2),全量验证绿(selfcheck 82/82、网关、回归 11),
  **106 已同步**(远端 selfcheck 82/82)
- **第六轮复审 PASS**(2026-10-13;报告 reviews_v2/phase_a_round6_review.md:
  5B-1 静态/语义/构造性三层核验 6/6,5N-1/2/3 落实,全量绿,HEAD=f0d75c3 纯净);
  **影子窗口已重启**(quant-shadow active,2 实例,boot 水位 13:12 已应用),
  **N=5 重计,起点=10-13 13:12**;水位文件将在首个成功 flush 节点后落盘
  (commit-on-flush 语义);10-20 差异清单提醒仍有效(窗口已于 13:12 重启,见上第六轮段)
- **通知位阶闸门+方向化标注(10-13 午,用户要求)**:用户报"支撑压力位置与方向矛盾"
  (快行情下结构位滞后于价的瞬时失配,自愈类)→ quant-webhook 加**位阶一致性闸门**
  (selection 三价须 支撑<挂单<压力,失配拦截+日志计数;价位缺失放行)+排版改
  **方向语义标注**(short=目标(下)/风险(上),long=目标(上)/风险(下));三网关回归过,
  已部署 106(c81696c),15:05 起新排版+双通道+闸门三合一生效
- **Day-2 午后里程碑(10-14 15:0x 全部 ✅)**:
  (1) **影子 1d 首评端到端打通**——14:59 两侧节点报告(RB0/CU0)+水位成功落盘
  {"RB0.SHFE":"2026-10-14T15:00:00"}(4B-9/4B-4/5B-1 修复链生产实证);框架侧
  entries_f=0 vs legacy trend_pullback=1(Y0)——差异=覆盖范围(影子仅 RB0/CU0,
  legacy 全市场扫描),非模型分歧;框架 evaluate 走 CHOP_RANGING 无方向跳过与
  legacy 扫描全跳过同因
  (2) **日线波段首跑 ✅**——15:00 节点 Y0 入选,submitted=1;生产已在运行
  重构版 poolscan(evaluate_product 行号实证)
  (3) 15:05 双通道未触发=**当日 market_pullback 扫描 0 入选**(9 品种全
  CHOP_RANGING 跳过,0 入选不推送属设计)——新排版/双通道/闸门的实战首秀
  待首个有入选的扫描日;--test 已验证双腿认证
- **Day-2 晨检(10-14 09:31)**:三服务 active;**晚盘补跑首次真实触发 ✅✅**——实测
  01:00:08 与 02:30:00 两次 RB0 late-night close detected(两层缺陷修复实战验证);
  runner errors=8 条全为 06:01 网络抖动自愈;**影子"零评估"澄清(非 bug)**:
  trend_pullback=1d 决策周期,每日仅 15:00 session_close 评估一次——重启后零节点
  报告属预期,首评节点=**今日 15:00**(应有 node report+watermarks_*.json 落盘);
  **待查**:昨日 15:40/16:22 两次非本会话的 quant-shadow 重启(操作者不明)
- **会话收尾(10-13 午后)**:三移交单(HO001/002/003)全部处置闭环;第六轮评审 PASS
  已归档(reviews_v2/round4/5/6 三份报告在库);影子 N=5 窗口 10-19 收线、
  **10-20 09:30 出差异清单提交用户确认**;**提醒迁移**:原会话挂有 10-14 09:30
  影子晨检(含晚盘首触确认)与 10-20 09:30 差异清单两提醒——新会话须重挂;
  15:00 日线波段首跑/15:05 双通道首秀的结果以 journal 与微信实收为准;
  水位文件(shadow_compare/watermarks_*.json)应在首个成功 flush 节点后出现
  (commit-on-flush 语义,缺失=5B-1 复发,立即查)

## 2026-10-13 15:29-15:45 新会话开场核验:暴露两缺陷(已定因,待用户决策)
- **15:00 日线波段首跑**: 扫描正常(Y0 long 入池),但 PA 提交被拒
  `bad_selection_timeframe`(submitted=0)——根因=引擎侧
  `vnpy_patiming/config.py` TIMEFRAME_MINUTES 白名单仅 1m~60m **无 1d**,
  日线波段→PA 链路结构性不通,首次实跑才暴露;修复候选=加 "1d":1440
  (engine 多处仅做分钟算术,低风险),须独立评审+04:00-05:15 窗口重启 patiming-engine。
- **quant-shadow 14:54:36 起静默挂死**: poll 主线程阻塞于
  feed.query_bar_history(无超时,无异常日志,进程 alive)→15:00 收线节点未评估
  →影子首日零产出(无报告/无 watermarks_*.json;5B-1 整改本身经查**无复发**,
  f0d75c3 的 self 解析在库在用)。已 `sudo -n systemctl restart`(新 PID 142456,
  boot 水位 15:40);加固方案(线程超时/静默看门狗/双管)待用户选。
- **framework_base.py:74-79 假警报**: 5N-1"实例优先"修复只落在
  selection_strategy.py,framework_base 内重复告警块仍旧 type(self) 类级查找
  →每次 boot 必报 `binding sink missing`(实际实例 sink 已绑,评估能力无碍)。
  cosmetic,并入下批评审。
- **15:00:37 双通道推送核验通过**: SC0(60m short)fanout 双腿成功
  (无 网关异常/fanout partial failure),位阶闸门未拦截。
- **Y0 信号未达用户(补记)**: Y0 long trend_pullback,支撑 8817/压力 9286,
  RR 2.68,BULL_TREND,valid_bars=12(1d)。是否窗口修复后手动补投待用户定。
- 本会话已重挂提醒: 10-14 09:30 影子晨检(含挂死处置指引)+10-20 09:30 差异清单
  (N=5 起算是否后移待用户定,决定后同步改提醒)。

## 2026-10-13 16:2x Round-7 评审+修复+即时部署(新会话首战全记录)
- **用户决策(4+1)**:引擎 1d 修复+明晨窗口部署;影子=超时+看门狗双管;N=5 自
  10-14 重计(差异清单挪 **10-21 09:30**,提醒已改);Y0 不补投等 10-14 15:00
  自然重扫;通知文案"盘后选品"→"选品通知"。
- **Round-7 独立评审 PASS-WITH-FINDINGS**(reviews_v2/phase_a_round7_review.md):
  MAJOR-1(stage/cron 未挂)当晚闭环;MINOR-2 文档随批修;MINOR-6 补两用例
  (1d sel>exec 接受+2d 拒;engine_extras 9 passed);MINOR-1/3/4/5 接受记 v2。
- **实施(vnpy=3b2d72d / quant-repo=28b2430,均已推)**:
  vnpy_patiming config +`"1d":1440`+engine 移除 selection_gt_exec(**1d 倒计时
  =自然日语义,12 bar≈12 自然日,偏保守,已知接受**);framework_boot 90s 有界
  取数+心跳文件;framework_base 5N-1 同步(boot 假警报根除);文案三处+HERMES
  两文档;deploy/ 四件套(引擎一次性部署脚本+影子看门狗脚本/单元)。
- **106 即时部署(16:23-16:28;备份后缀 .bak_20261013_r7)**:poolscan/
  framework_boot/framework_base→/opt/aiprj/selection;**gateway→/opt/aiprj/services/**
  (quant-webhook 实际运行路径;首装误至 selection/services,已纠正——该处副本
  也同步更新但服务不消费);三服务重启全 active;**boot 无假警报**;心跳就位;
  quant-shadow-watchdog.timer enabled(active/5min);零 Traceback。**远端 gateway
  补齐了落后 HEAD 的位阶闸门+方向化标签**(10-13 午"已部署 c81696c"对 gateway
  文件不成立,系漏同步,已纠正)。**端到端已验证**:注入 TEST.SHFE 选品样例→
  新标题【选品通知】+位阶闸门通过+fanout 双腿+队列清空(用户两通道应已收到
  一条 TEST 测试;窗口=3s/max_staleness=30s/队列 quant:queue:signals@6381/0)。
- **引擎窗口部署就绪(MAJOR-1 闭环)**:/home/tony/engine_stage_20261014 md5==
  脚本常量逐位一致;/etc/cron.d/patiming-engine-deploy-20261014 已挂
  (5 4 14 10 * root);窗口外试跑=正确 NO-OP 且 cron 保留。**10-14 04:05 自启,
  核验:journalctl -t engine-deploy --since '2026-10-14 04:00'**。
- **⚠️ vnpy 推送远端=fork/patiming-production**(origin=上游公共仓 vnpy/vnpy,
  403 不可推;fork/master=官方上游历史,勿混推)。
- 新选品排版首次真实双通道=今夜夜盘 60m 收线起;影子首个评估节点=10-14 15:00
  (框架侧);晚盘补跑首触仍=10-14 凌晨 01:00/02:30。

## 2026-10-13 22:2x WEBHOOK_SECRET 轮换(进行中)+HO004 排期+研究侧入库
- **研究侧入库**:RS015/RS016/DEC005/HO004(final)+GT rev2 标签+4 脚本,22 文件
  da9e96f5 已推。HO004 工程实施已排入待办(见上)。
- **轮换(用户 10-13 晚指定新值;新值不入任何 GitHub 文件,交接只记状态)**:
  - ✅ Android:`cloudwebhook-android/local.properties` 已改(gitignored 实证);
    **⚠️ 手机上已装 APK 仍持旧值,Worker 切新后旧 APK 会被拒——需重建安装**
    (gradle 本机可构建,sdk.dir 在;待用户令);
  - ⏳ Worker:本机 wrangler 未认证,两条路=用户面板改 Secret(WEBHOOK_SECRET)
    或 `npx wrangler login` 后代执行 `secret put`;**Worker 未切前 106 不动**;
  - ⏳ 106:`/opt/aiprj/services/gateway_config.yaml` 行 25 custom_secret+行 29
    custom.secret 两处待切+重启 quant-webhook+TEST 注入端到端验证(备妥待发);
  - 老值遗留说明:仓内 HEAD 已零残留(e662ac7 脱敏),仅历史提交与 106/旧 APK 存量。
- **死循环排查(用户报,22:16)**:生产端零循环——四服务 NRestarts=0,夜盘影子
  每分钟正常喂条,22:00 收线仅 1 条推送(AU0),Hermes 零错误;疑为 GUI 选项框
  渲染问题,与生产无关。
- **统一出口 v1 实施(10-14 00:0x-00:2x,设计 3f8c49f/实施 68b75d3/修订 1f83d70)**:
  用户明确需求=选品+择时**同时同格式**发 cloudwebhook 和 hermes;Hermes 自产
  消息(分工功能)与本项目无关不动。实施:patiming_webhook 收敛为 stream→统一
  队列薄桥(自渲染/自 fanout 删除);网关迁入 timing 渲染分支+topic 按类目
  (selection=pa-latest-monitor/timing=pa-signal,config 可覆盖);webhook_queue.py
  "script ignored" 读码定性=设计内行为(故意无 stdout,投递归 watchdog),不修。
- **Round-8 独立评审 PASS-WITH-FINDINGS**(reviews_v2/phase_a_round8_review.md):
  M-1 test_mode 隔离失效→已修+回归护栏(14 passed);M-2 保守解=部署脚本向 106
  config 插 topic_timing: pa-latest-monitor(App 行为保持现状,pa-signal 待用户
  确认订阅后再切);M-3 密钥轮换**与本批解耦**(与 Worker 原子协同另行安排,
  避免单腿 401 连锁停摆)。format_signals 新旧版 7 组用例逐字节一致、timing
  布局 4 组逐行 IDENTICAL(评审机械验证)。
- **部署就绪(10-14 04:15 一次性 cron 已挂+试跑 NO-OP 验证)**:
  /etc/cron.d/notify-unified-deploy-20261014;硬要求已编码=仅同步 2 个 .py
  (md5 2270a8a9/45483cfe=stage 逐位一致)、**重启顺序 quant-webhook 先于
  patiming-webhook**、回滚反序、config 备份+yaml 校验、严禁覆盖 106 config
  其余内容;核验 journalctl -t notify-deploy。晨检提醒已含两部署核验。
- **遗留(用户侧)**:①Worker Secret 切换(面板/wrangler login)+APK 重建;
  ②App 对 pa-signal 主题订阅确认(确认前 timing 落 pa-latest-monitor 保持现状);
  ③WEBHOOK_SECRET 五处同值轮换(与 Worker 原子协同,方案见统一出口设计稿);
  ④ 统一后首晚观察两通道同文同时到达(晨检 ⑨)。
- **晚间旧格式微信消息定性(23:4x,用户确认)**:21:02:44 的【盘后选品】旧版式
  消息=**Hermes 自己的分工功能所发**(非生产选品链路;当晚 21:00 生产端零运行,
  网关/Hermes 路由队列均无痕迹)。**用户裁定:保留,不处理**。
- **cloudwebhook 腿端到端健康实证**:直探 Worker(hook.quaiin.link)返回
  {ok:true,topic:pa-latest-monitor}→手机 app "just now" 收到;gateway→Worker
  22:42 同样 2xx。**注意 topic 路由**:selection 类被 Worker 归入
  `pa-latest-monitor` 主题——app 推送通知与该主题的订阅/免打扰关系待用户核对。
- **🔴 统一发送出口(用户指令,设计议题留下次会话,先出方案再审)**:
  现状=微信(Hermes 侧,含分工功能+webhook 路由两套)与 cloudwebhook(App 侧)
  各自独立,配置/密钥/故障面割裂;hermes /webhooks/ops 路由对网关推送存在
  **"script ignored" 静默不执行**(gateway.log 16:28:32 实证,即使 2xx)。目标:
  单一发送入口、两接收方同源同文、一套密钥。方案候选:①网关唯一出口,hermes
  路由修活(查 ignored 判定);②微信侧完全交分工功能,网关仅保留 cloudwebhook
  腿。**待用户选型后再动**。轮换未完项:Worker Secret(用户面板/wrangler login
  二选一)→106 gateway_config 两处→Hermes config platform+weixin+ops 三处
  (同为旧值,须同批切)→TEST 端到端;新值不入任何 GitHub 文件。

## 2026-10-14 午后:HO004 实施 + HO005 阶段 0+1 安全子集(评审中)
- **HO004 已实施**(vnpy a269f8e0+bbba8078):ContextTaggerV1 A1 退役 v1
  reversal/A2 R-C v2 实装(占位 trend 前,参考=研究侧 rev_C 逐行对齐)/
  B4 DT/DB 背景 {range,reversal}→{range}(detectors :445 一处,W_BOTTOM 默认关
  不动)/export-context-v2 模式+自检(占比区间 25-45%);测试 4 passed+全套件
  80 passed(2 环境失败存量);两处测试语义随批更新(B4 背景 range 化、
  validity 用例按守卫移除新语义+新增真负例)。
- **HO005 阶段 0+1 安全子集已实施**(quant-repo 3d3ded7+bc2752e):A1 粘性修复
  (resolved 每键每日 ≥2 次重检,检出变更→重订阅+换月事件)/B1 contract_code/
  A2 换月事件走统一队列(网关新增 🔄 【主力换月】渲染分支)/网关 category 三态。
- **两项工程裁决(已记录 round-9 骨架)**:①B2 偏差=rollover_policy 不入 PA
  指令(引擎 _clean 丢未知键,入 content_hash 需改引擎,违反 HO005 边界 E)→
  expire 语义由 runner 侧 strategy_selection_revoke 实现;②**HO005 前提问题
  已上报**:RS018 审计前提"任务单 symbol=具体合约"与 as-built 不符(生产全链
  连续符号 rb0.SHFE,数据源自动跟随换月),P1 粘性在 monitor 类(生产 selection
  路径不实例化)——一致性检查/REVOKE 部分**暂缓**待研究侧确认。
- **Round-9 独立评审 PASS-WITH-FINDINGS（有条件放行 10-15 04:00-05:15）**
  (reviews_v2/phase_a_round9_review.md 已归档):条件四件+MAJ-1/MAJ-3 全部闭环——
  ①stage 四文件 md5=脚本常量逐位一致(59a559fd/d7b89eea/648b6099/5a723c3d,
  poolscan=Windows 工作树 CRLF 原件,MAJ-2);②改前版 baseline_backtest.py
  (md5 690994db)已预置 /opt/aiprj/vnpy_patiming/(备份/回滚可用);③脚本 0755+
  cron 0644 已装;④MAJ-1 节流跨日清零已修+MAJ-3 runner 检查 PID 化已修
  (md5 同步 648b6099+重跑)。试跑 NO-OP 验证过(cron 保留)。
- **Round-9 发现账本(MINOR×6,不阻塞)**:R-C f_half 角点偏差(工程比参考宽松,
  可构造反例);HO005-A3 旧合约预警抑制未实现未记录;rollover payload 缺
  affected_instructions;rollover topic 回落 base topic;主力判定无防抖滞回;
  窗口闸门仅认 hour==04 无干跑模式。→ 记入下次迭代清单。
- **✅ 部署已执行(10-14 22:2x,用户授权 --force-now 窗口外)**:全链 DEPLOY_OK
  (stage→安装→PID 级重启验证→selfcheck→preflight 6/6);四文件盘上 md5 全中
  (59a559fd/d7b89eea/648b6099/5a723c3d);五服务 active;cron 已消费;脚本已加
  --force-now(跳日期+小时闸门,其余门禁全保留)并入库。部署后冒烟:patiming
  --test → 双通道到达 ✓。**B4 即效影响(已生效)**:生产 DT/DB 在 reversal 窗
  少 ~12% 事件(研究侧量化批准)。
- **🔴 A3 导出已交付+一项观察**:`vnpy_patiming/output/baseline/context_tags_v2/`
  六品种 CSV(122,546 行;按惯例不入库);自检 reversal 占比 **51.7%**(全 K 分母)
  高于研究侧网格口径 36.2%——分母不同(GT 抽样网格 vs 全 K)+EMA/ATR 实现差异;
  **最终判定=研究侧 B1/B2 验收**(预注册:B2 失败→回滚 A2 保留 A1);自检状态
  CHECK_NEEDED 如实保留待研究侧判读。
- **前提问题(待研究侧答复,不阻塞本批)**:RS018 审计前提"任务单 symbol=具体
  合约"与 as-built 连续符号链不符→一致性检查/REVOKE 暂缓(见上轮裁决)。
  ⚠️ 本胶囊正被研究侧会话并行编辑——**写后立即 commit**;其新一批产出
  (RS017/019/020/021、HO006、DEC006、MTG006 等)尚未入库,归其会话收尾。

## 2026-10-15 00:3x 分频道协同切换完成
- cloudwebhook Android 多主题订阅实施完毕（用户侧确认）；上游协同已执行：
  gateway_config `topic_timing: pa-signal`（备份 .bak_topicswitch_20261015）+
  quant-webhook 重启（首次漏 sudo 被拒已补）+ timing 注入 e2e 推送 ✓。
  **当前 topic 路由：selection/rollover→pa-latest-monitor；timing→pa-signal**。
- 待用户确认：App ⚡ 渠道收到 00:34 的 TEST（00:33 那条走的是切换前旧主题）。
- **轮换终态(00:3x-01:1x 与 cloudwebhook 会话对齐)**:Worker 线上仍=旧值
  (双会话探针一致:新值 401/旧值 400 过认证)——**等待用户在 Cloudflare 面板
  保存 WEBHOOK_SECRET=新值**(唯一剩余动作,面板属用户权限);保存后
  cloudwebhook 侧自动:鉴权探针→R2 上传 **v1.3.0 APK**→验证 /apk/latest。
  我侧网关 config 已=新值(勿再动);Hermes 三处=新值 ✓。
- **⚠️ 过渡期行为(10-15 04:15 起)**:timing 消息 topic=pa-signal——**App
  v1.2.3 单主题订阅收不到**(微信腿正常);App 升级 v1.3.0(多主题)后方可
  见 ⚡ 渠道。双通道 A1-A4 验收前置=手机升 v1.3.0(cloudwebhook 会话对齐)。
- 明晨 09:30 提醒已挂:HO004+HO005 部署核验+轮换状态+影子第 2 天。

## 2026-10-15 00:3x-01:0x WEBHOOK_SECRET 轮换实战(中间态,服务已恢复)
- **事实链**:用户在**本机**更新了 CUSTOM_WEBHOOK_SECRET(未部署到 Cloudflare
  线上)→ Worker 线上仍=旧值(探测实证:旧密钥过认证[400=探针 body 瑕疵非鉴权],
  新密钥 401 拒)→ 我按"已更新"理解把网关 custom+Hermes 三处切新 → 双腿 401
  (custom 对 Worker 不匹配;hermes 对网关不匹配[网关尚未重启时]/后自洽)→
  **已回滚网关 custom 两处到旧值并重启,服务恢复**(post-restart 0 异常;
  直注 Worker 2xx + App 收到 TEST2)。
- **当前混合态(各自自洽,无影响)**:hermes 家族(gateway 腿 secret+Hermes
  config 三处)=**新值**已自洽;custom 家族(网关 2 处+Worker 线上)=**旧值**
  自洽;App 收推送无鉴权不受任何影响;local.properties 新值=死配置(app/src
  零引用)。
- **收尾(一步,待用户)**:用户在 Cloudflare 面板把 Worker 的
  **WEBHOOK_SECRET**(index.js 读取的 env 名;即其所谓 CUSTOM_WEBHOOK_SECRET)
  更新为新值并生效 → 回我一声 → 我 sed 网关 custom 两处回新值+重启 →
  TEST 端到端 → 轮换闭环。
- 教训:轮换类操作"已更新"必须问清"更新到哪一层"(本机文件/线上 env);
  探针先于切换(用双值探测定线上一态,再动服务端)。

## 2026-10-14 15:10 关键节点复核:全过 ✅
- **Y0 日线波段首次提交成功**:15:00:40 submitted=1 skipped=0(引擎 1d 生效后
  首战);无 bad_selection_timeframe;引擎已接受并完成 y0.DCE/60m warmup
  (42 bars ready)——任务单进入监控。
- **影子首次评估+水位落盘**:shadow_20261014_1500_trend_pullback_{RB0,CU0}_1d.json
  双实例报告 + watermarks_{RB0,CU0}_1d.json = 2026-10-14T15:00:00(commit-on-flush
  首次实战)。**N=5 影子窗口正式开账(10-14~10-20 含今日)**。
- **通知链路**:桥转发了引擎流事件(15:00:03)→网关 15:00:06 推送双通道;
  今日 15:00 60m 选品 0 entries(无推送,正常)。HO002 零误开。
- 后续:15:00 节点逐日由 runner 自动运行;10-15 04:05 HO004+HO005 窗口部署;
  10-21 09:30 差异清单。

## 2026-10-14 09:30 晨检+10:26 引擎重跑(1d 已生效)
- **晨检**:通知出口 04:15 部署 DEPLOY_OK(bridge 正常,topic_timing=pa-latest-monitor
  已插);影子夜盘 136 次 poll fed;**晚盘首触成功**(01:00:08+02:30:00,10-13 修复
  首次实战通过);看门狗零事件;HO002 零误开;watermarks 未现=符合预期。
- **❌→✅ 04:05 引擎部署假阳性回滚→10:26 用户批准重跑成功**:新代码启动本已
  正常,脚本 `grep Traceback` 命中**旧进程关闭噪音**(uvicorn SIGTERM 必打
  KeyboardInterrupt)误判回滚;验证已修=只查新进程 PID+正向断言"Starting MCP
  server",引擎脚本加 `--force-now`(仅跳小时闸门);**10:26 --force-now 重跑
  DEPLOY_OK**(preflight 6/6,盘上 md5=b230dd07/636cb3d7,运行态 1d=1440 实证,
  守卫仅存注释 :390)。**今日 15:00 Y0 应首次提交成功**(15:10 提醒复核)。
- **并行会话核查**:其"周四 04:05 引擎部署任务"经全系统核查(cron/crontab/
  hermes cron.db/systemd timers)**不存在可执行体**=其会话内提醒(跨会话不执行),
  本批重跑无冲突;其 04:07 runner 重启/04:15 hermes profile 密钥修复无文件冲突
  (runner/poolscan md5 与已知一致)。⚠️ 本文件 09:35 版曾被并行会话保存覆盖
  (晨检段丢失,本次重加)——**并发编辑胶囊须写后立即 commit**。

## Phase A 待办(设计稿 §3 行 1-13;完成后再送第四轮独立评审)
- [x] #10 15m 桶语义 / #11 1d 触发时效(60m 链路 15:00) / #12 tf_selector 模块+单测 / #13 部分(全败不推进/告警限频/规则预校验)
- [x] #10-12 收尾: tf_selector 接线两模型+pool_config 键(10-13 上午完成;poolscan 新版已部署 106)
- [x] #13 余项: 旧 id 排空查询按 legacy 精确形状(identity.is_legacy_instruction_id/select_legacy_ids)、文档统一 replace_scanner_entries 命名
- [x] #1 具体策略类(718d7db:framework_base+两具体类,与 template 1.3.0 逐条对齐);[x] 壳生命周期离线测试(桩 vnpy BarGenerator)+set_bindings 修复
- [x] #2 trend_pullback 提取 evaluate_product(poolscan.py,行为保持,已部署 106)
- [x] #3 InstructionSink 接线 boot(PhaseBError 代码层门禁,评审 PASS 前不可开)
- [x] #4 影子对比器接线(4B-3 事件化 ShadowNodeRecorder,每 close 节点一份报告)
- [x] #5 universe→settings 生成器(strategy_framework/universe.py,解析失败告警+跳过)
- [x] #6 boot 集成(framework_boot 影子跑;quant-shadow.service systemd 常驻)
- [x] #7 venv 安装 vnpy_portfoliostrategy 1.3.0(本地+106)
- [ ] #8 旧 id 指令排空执行(脚本就绪 drain_legacy_instructions.py,plan 默认/apply 双门禁;**执行待用户令**)
- [ ] #9 通知模板(引擎侧,Phase C)
- [ ] **HO004 工程实施(排期:下一会话窗口;用户 10-13 晚确认排入计划)**——移交单
  final(用户已批"同意工程改造",strategy_research/60_decisions/HO004*.md):
  A1 退役旧 reversal 规则(EMA 斜率×差值异号+5 根反向位移)/A2 实装 R-C v2
  (先行腿 20 根极值幅度≥2.0×ATR+自极值反向位移≥1.0×ATR+回撤比例≥0.5,
  占位于 trend 分支前)/A3 导出 `vnpy_patiming/output/baseline/context_tags_v2/`
  新目录(v1 目录保留)+自检占比区间按 ~36% 更新;零交易风险(判定侧仪表,
  编排不消费 reversal);实施后研究侧 B1-B3 验收(脚本已备 ho004_acceptance.py);
  **实施须独立评审**;B4 消费方迁移(S-003 DT 背景 {range,reversal}→{range})
  随交付登记
- 2026-10-13 晚清单核对:上述补勾各项均见于当日叙述段,原清单漏勾,本次补记;
  round-7 增量(引擎 1d/看门狗/文案)见 16:2x 段。**门状态:影子跑中(N=5=10-14~10-20),
  10-21 09:30 差异清单提交用户确认后进 Phase B**
- **门**: Phase A 完成自检→第四轮独立评审→PASS→影子跑(ShadowSink,≥N 交易日)→差异清单用户确认→Phase B 切换(旧 runner .bak+cron 回滚)→质量跟踪(胜率/RR 达成/出场复盘)→二期择时归化→退役旧池引擎

## 2026-10-15 晨 · 选品通知重复 + cloudwebhook 收不到(双症同因,已修复)
- **症状(用户报)**: 同一条 CU0 选品通知在 hermes 微信收到多次(标题时间戳每次不同,如 07:43:23);
  cloudwebhook 一条未收到。
- **根因链**:
  ① **通道失配**: 客户端/Worker 侧今日 **00:51:56** 已轮换到**新 12 字符**值
     (cloudwebhook-android `local.properties` 实证),106 侧 `gateway_config.yaml` 与
     `/home/tony/.hermes/.env` 仍是**旧 10 字符**值(`2ef60b6cb4`,自 ≤10-13 未轮换)
     → custom 腿自 **00:55:44** 起 100% `401 Unauthorized`
     (今日累计 1 万+行日志,约 5200 次请求);hermes 腿独自承担投递。
  ② **重试风暴(重复的真因,非防抖)**: `FanoutSender` 部分失败时保留**全部** target pending,
     `gateway_loop` 仅在整批成功后 `buffer.clear()` → 坏通道把好通道一起拖入每 ~3-4s 一轮的
     **无界重试**。实证: 02:30:23 起 401 异常 **5181** 次、"已推送"=0、内存 buffer 里卡着
     02:30 的 CU0 → 每轮用 `datetime.now()` 重渲染标题,这才是用户看到多个不同时间戳同一条的机制。
    (防抖 window=3s / max_staleness=30s 本身工作正常。)
- **处置(用户令"修复"/"106改新")**: 先 `stop quant-webhook`(落掉内存 buffer,避免 02:30 过期信号
  在通道恢复后补推)→ 备份 → 106 三处 secret 改为 Worker 实测可接受值(`gateway_config.yaml`
  的 custom_secret + custom.secret、`/home/tony/.hermes/.env` 的 WEBHOOK_SECRET)→ 起服 →
  TEST 注入验证。**实证**: 直连 Worker 旧值(10 字符) 401 / 新值(12 字符) 200; 注入后
  `已推送 1 条合并信号`(两腿全成),重启后 401=0、CU0 补推=0、队列 llen=0、yaml 可解析、
  与修复前仅差 secret 值(文件 1549→1553B = 10 字符带引号 → 12 字符带引号,引号风格已还原)。
- **备份**: `gateway_config.yaml.bak_secretfix_20261015_082246`、`.bak_precleanup_0824xx`、
  `.bak_quotestyle_08xx`、`/home/tony/.hermes/.env.bak_secretfix_20261015_082246`(值未落任何日志)。
- **偏差与更正**:
  ① 本次 restart 落在 **08:22**(非 04:00-05:15 窗口): 重试风暴只能靠停进程清内存 buffer,
     属必要例外(服务当时已在故障态且持续打扰用户);
  ② **更正(本会话自查,勿沿用早前表述)**: 曾据 python 正则把"另一写入者/值 sha `a4c44bfaaf`"
     写入记录——实为**测量假象**: 该正则把值的**双引号计入长度**,`a4c44bfaaf` = 带引号旧值的
     sha。事实核对: `.bak_secret_20261015_2` 与本批备份**逐字节相同**(md5 `471bab78…`),
     106 旧值一直是 10 字符带引号,**无并发写入者**;现 106 三处 = 与 Worker/客户端一致的
     12 字符值 `7bc2c8e581`。教训: 比对 secret 一律**先剥引号**(`awk`/yaml 解析),勿用裸
     `\S+` 直接哈希整段。
  ③ **未做(需独立评审)**: `FanoutSender` 仍非幂等(任一腿永久失败 → 无界重复推送),且卡在
     buffer 里的信号绕过 max_staleness 过期闸门 → 见 `60_decisions/HO007`(草案待批)。
- **顺带**: HO006 两项仍未部署(`/opt/aiprj/data` 不存在 → `selection_tracking.jsonl` 无;
  `poolscan.py:160` 武装列表仍为 `["ema_pullback","structure_pullback"]`)。
- **HO007 通知网关加固(当日 10:13 已上线, quant-repo=97a4896)**: 三轮独立评审
  (一轮 PASS-WITH-FINDINGS 并实证 **D1 真实存量缺陷**=首个成功批次后每批零请求却记
  "已推送";二轮确认整改并新发现 round-2 MAJOR=重试被新到信号拖延+暂存信号被 A3 整批
  老化(探针 20 丢 13);三轮 delta 复核 PASS,变异验证非空转,60 信号快流死腿探针
  60/60 恰好一次 0 重复)。落地: A1 幂等 fanout(只重试失败腿)/D1 `start_batch` 批次
  完成语义/A2 批次预算钳制进时效预算(`attempt_budget`)+放弃日志附符号/A3 出队与发送前
  共用 `_signal_age/_is_stale`/`--test` 非 fanout `targets` 未绑定(存量)顺带修。
  部署 10:13 守卫式 `--force-now` **DEPLOY_OK** `gw_md5=8eb7fd4f`,smoke 两批次双通道
  全达(旧代码第二批为幻影=D1 生产实证);脚本 `deploy/ho007_gateway_deploy_20261015.sh`
  (RUNBOOK 台账已记)。遗留 INFO: at-least-once(接收端按 signal_id 去重可消)、进程崩溃
  丢内存批次(ack 队列,超范围)、`test_gateway_live.py` 需本地 redis+config 才能跑。
  测试基线: `tests/test_webhook_gateway.py` 16 例 + `test_patiming_webhook.py` 5 例
  全绿(venv=D:\AIprj\vnpy\.venv);本机 httpx loopback 需 `NO_PROXY=127.0.0.1,localhost`
  (注册表代理 ProxyServer=127.0.0.1:7890 被 httpx 采信,非代码问题)。

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

## 附录:10-13 晚~10-14 晨会话增补(部署核验会话)
- **周二 04:05 自动部署实核**: DEPLOY_OK 全链(stage verified→installed→restarted→selfcheck 28/28→preflight 6/6→hermes 重启),md5 三件/DEPLOYED 标记/双备份全中
- **晚盘补扫首次真实触发** ✅: 10-14 01:00:08 与 02:30:00 双节点 detected+processed(核心修复实盘生效);日线波段首跑 15:00:37 Y0 入选(entries=1)但提交被引擎拒 bad_selection_timeframe——根因=服务器 /opt/aiprj/vnpy_patiming/config.py 缺 1d:1440(3b2d72dc 已提交未部署);**周四 04:05 窗口任务已挂**(守卫式部署+引擎/runner 重启+1440 验证,若已被并行会话部署则自动跳过)
- **hermes profile 密钥修复完成**(10-14 04:15): 8 个 profile .env 全部补 GLM/DEEPSEEK×3(值未落日志),重启 active;04:15 后 empty/unset=0。根因=hermes profile 作用域密钥隔离(secret_scope.get_secret 不回退 os.environ,设计如此),/etc/environment 全局键对 profile 内读取不可见——新键入 profile .env 而非全局
- **10-14 晨 06:01 DNS 抖动第三连**(Errno -2 Name or service not known,runner 侧,自愈);连续三日 ~06:00,建议查路由器/PPPoE/resolved
- **09:00 桶抑制说明**: 10-14 04:07 runner 重启后首个 09:00 桶按开盘桶抑制设计跳过,当日首个评估节点=10:00(预期行为,非缺陷)
- **工具**: pwsh→ssh 复杂脚本用 `base64 -d | bash` 已多轮实证可靠;远程单行内层禁用双引号

## 用户偏好/纪律(累计)
UI 界面优先,拒绝 SSH 日常使用;升级/重启只允许凌晨 04:00-05:15 窗口;决策类先问再做;单套 vnpy 不分叉,不重复造轮子;研究回测盘后跑与生产零耦合;**实施完成必须独立评审,通过才能提交部署**;流程图/设计稿先审后做;上下文不稳时以本胶囊+todo 为准,勿凭记忆;**同一任务执行超 20 分钟仍在原地打转=立即中断出来,先解决问题再重新执行(2026-10-13 晚新增;适用于命令反复失败重试/依赖安装卡顿/等外部响应/会话内反复无进展等一切场景——先诊断根因,处置后重跑,禁止干耗)**。
