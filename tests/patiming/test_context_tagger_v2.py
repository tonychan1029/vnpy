"""HO004：ContextTaggerV1 reversal v2（R-C）行为测试（A1 退役 + A2 实装）。

参考实现 = strategy_research/code/analysis/context_v2_diagnostic.py rev_C
（LEG_K=2.0 / CTRP_K=1.0 / RETR_K=0.5；占位 hi：reversal 提到 trend 之前）。
"""

from vnpy_patiming.baseline_backtest import ContextTaggerV1


def test_rc_down_leg_reversal_fires() -> None:
    """先升后跌：腿 ≥2×ATR、自高点回落 ≥1×ATR、回撤比 ≥0.5 → reversal。"""
    atr = 10.0
    i = 60
    closes = [100.0] * (i + 1)
    for j in range(45, i - 3):      # 45..56 线性拉升 100→111
        closes[j] = 100.0 + (j - 45)
    closes[i - 3] = 130.0           # H20（近 20 根最高，腿端）
    closes[i] = 115.0               # 自高点回落 15=1.5×ATR；回撤比 0.5 → 触发
    tagger = ContextTaggerV1(exit_streak=5)
    ema_history = [105.0] * 6       # slope=0；diff=10>0.5×ATR → range/trend 不抢
    tag, strict = tagger.update(closes, ema_history, i, atr)
    assert tag == "reversal"
    assert strict == 0


def test_v1_style_reversal_without_leg_no_longer_fires() -> None:
    """A1 退役护栏：斜率×位置异号 + 5 根 1×ATR 反向位移，但无先行腿 → 非 reversal。"""
    atr = 10.0
    i = 60
    closes = [100.0] * (i + 1)
    closes[i] = 100.0 - 1.2 * atr   # 当前根下移 1.2×ATR（5 根窗内反向位移 ≥1×ATR）
    tagger = ContextTaggerV1(exit_streak=5)
    ema_history = [100.2, 100.2, 100.2, 100.2, 100.3, 100.5]  # slope>0 与 diff<0 异号
    tag, _ = tagger.update(closes, ema_history, i, atr)
    assert tag != "reversal"        # v1 旧规则会触发，v2（无先行腿）不再触发
    assert tag == "trend_channel"


def test_breakout_hysteresis_unchanged() -> None:
    """B3 护栏：breakout 迟滞（enter2/exit5）行为不受 A1/A2 影响。"""
    atr = 10.0
    i = 60
    closes = [100.0] * (i + 1)
    closes[i - 2] = 150.0           # 抬高 40 根窗上缘 → 阈值 150+0.1×ATR=151
    closes[i - 1] = 152.0           # raw 第 1 根
    closes[i] = 153.0               # raw 第 2 根 → in_breakout（enter2）
    tagger = ContextTaggerV1(exit_streak=5)
    ema_history = [100.0] * 6
    tag = ""
    for j in range(40, i + 1):      # 迟滞是跨调用状态：须逐根喂入
        tag, _ = tagger.update(closes, ema_history, j, atr)
    assert tag == "breakout"


def test_rc_requires_both_retrace_and_ratio() -> None:
    """腿够大但回撤不足 1×ATR → 不触发（R-C 三条件缺一不可）。"""
    atr = 10.0
    i = 60
    closes = [100.0] * (i + 1)
    for j in range(45, i - 3):
        closes[j] = 100.0 + (j - 45)
    closes[i - 3] = 130.0
    closes[i] = 124.0               # 回落仅 6=0.6×ATR < 1×ATR
    tagger = ContextTaggerV1(exit_streak=5)
    ema_history = [105.0] * 6
    tag, _ = tagger.update(closes, ema_history, i, atr)
    assert tag != "reversal"
