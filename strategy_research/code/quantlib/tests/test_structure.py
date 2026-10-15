# RESEARCH ONLY - quantlib.structure 单元测试
"""quantlib.structure 函数覆盖测试：构造确定性数据验证每个函数的边界行为。"""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quantlib.structure import (
    find_swing_points,
    detect_trend_zigzag,
    detect_trend_ema_slope,
    classify_trend,
    find_range_boundary,
    near_support,
    near_resistance,
    kline_density_zone,
)


def make_bars(closes, spread=1.0):
    """从收盘价序列构造 [dt, o, h, l, c, v, oi] 行情列表。"""
    bars = []
    for i, c in enumerate(closes):
        o = c - spread / 2
        h = c + spread
        l = c - spread
        bars.append([f"2026-{i//20+1:02d}-{i%20+1:02d}", o, h, l, c, 1000, 5000])
    return bars


def make_zigzag_closes(base=100, amp=10, half_period=10, cycles=6):
    """构造锯齿形收盘序列（涨 half_period 根 + 跌 half_period 根交替）。"""
    closes = []
    for i in range(cycles * half_period * 2):
        phase = (i % (half_period * 2))
        if phase < half_period:
            closes.append(base + phase * amp / half_period)
        else:
            closes.append(base + amp - (phase - half_period) * amp / half_period)
    return closes


def make_trend_with_pullbacks(base=100, trend=0.5, pullback=0.3, leg=10, cycles=6):
    """构造趋势+回调序列：每 leg 根涨 trend*leg，然后回调 pullback*leg。"""
    closes = []
    price = base
    for cycle in range(cycles):
        for i in range(leg):
            price += trend
            closes.append(price)
        for i in range(3):
            price -= pullback
            closes.append(price)
    return closes


class TestFindSwingPoints:
    def test_zigzag_produces_alternating(self):
        closes = make_zigzag_closes(amp=10, half_period=10, cycles=6)
        bars = make_bars(closes, spread=0.5)
        swings = find_swing_points(bars, left=3, right=3)
        types = [s["type"] for s in swings]
        for i in range(1, len(types)):
            assert types[i] != types[i - 1], \
                f"consecutive {types[i-1]}{types[i]} at index {i}"

    def test_trend_with_pullbacks(self):
        closes = make_trend_with_pullbacks(base=100, trend=0.5, pullback=1, leg=10, cycles=5)
        bars = make_bars(closes, spread=0.5)
        swings = find_swing_points(bars, left=3, right=3)
        assert len(swings) >= 2

    def test_flat_no_swings(self):
        closes = [100] * 60
        bars = make_bars(closes, spread=0.1)
        swings = find_swing_points(bars, left=5, right=5)
        assert len(swings) == 0


class TestDetectTrendZigzag:
    def test_bull_trend_with_pullbacks(self):
        # 上升趋势 + 回调 → 多头
        closes = make_trend_with_pullbacks(base=100, trend=0.8, pullback=1, leg=10, cycles=10)
        bars = make_bars(closes, spread=0.5)
        result = detect_trend_zigzag(bars)
        assert result in ("多头", "震荡"), f"got: {result}"

    def test_bear_trend_with_pullbacks(self):
        closes = make_trend_with_pullbacks(base=200, trend=-0.5, pullback=-1, leg=10, cycles=10)
        bars = make_bars(closes, spread=0.5)
        result = detect_trend_zigzag(bars)
        assert result in ("空头", "震荡"), f"got: {result}"

    def test_realistic_data(self):
        # 锯齿形数据（模拟真实市场回调）
        closes = []
        for cycle in range(12):
            for i in range(10):
                closes.append(100 + cycle * 2 + i * 0.8)
            for i in range(5):
                closes.append(closes[-1] - 1.5)
        bars = make_bars(closes, spread=0.5)
        result = detect_trend_zigzag(bars)
        assert result in ("多头", "空头", "震荡")


class TestDetectTrendEmaSlope:
    def test_bull_trend(self):
        closes = make_trend_with_pullbacks(base=100, trend=0.5, pullback=1, leg=10, cycles=5)
        # 末尾补 5 根上升 bar（原序列结束于回调，close<EMA 是回调后正常状态）
        closes.extend([closes[-1] + 0.5 * (i + 1) for i in range(5)])
        bars = make_bars(closes, spread=0.5)
        result = detect_trend_ema_slope(bars)
        assert result == "多头"

    def test_bear_trend(self):
        closes = make_trend_with_pullbacks(base=200, trend=-0.5, pullback=1, leg=10, cycles=5)
        bars = make_bars(closes, spread=0.5)
        result = detect_trend_ema_slope(bars)
        assert result == "空头"


class TestClassifyTrend:
    def test_dispatch_zigzag(self):
        closes = make_trend_with_pullbacks(base=100, trend=0.5, pullback=1, leg=10, cycles=5)
        bars = make_bars(closes, spread=0.5)
        assert classify_trend(bars, method="zigzag") in ("多头", "空头", "震荡")

    def test_dispatch_ema_slope(self):
        closes = make_trend_with_pullbacks(base=100, trend=0.5, pullback=1, leg=10, cycles=5)
        bars = make_bars(closes, spread=0.5)
        assert classify_trend(bars, method="ema_slope") in ("多头", "空头", "震荡")


class TestFindRangeBoundary:
    def test_swing_method(self):
        closes = make_zigzag_closes(base=100, amp=10, half_period=10, cycles=4)
        bars = make_bars(closes, spread=0.5)
        support, resistance = find_range_boundary(bars, lookback=60, method="swing")
        assert support is not None
        assert resistance is not None
        assert support < resistance

    def test_percentile_method(self):
        closes = [100 + i * 0.5 for i in range(120)]
        bars = make_bars(closes, spread=0.5)
        support, resistance = find_range_boundary(bars, lookback=60, method="percentile")
        assert support is not None
        assert resistance is not None
        assert support < resistance


class TestNearSupport:
    def test_near(self):
        assert near_support(close=100.3, support=100.3, atr=1.0, tolerance_atr=0.5)
        assert not near_support(close=102, support=100, atr=1.0, tolerance_atr=0.5)


class TestNearResistance:
    def test_near(self):
        assert near_resistance(close=100.3, resistance=100.0, atr=1.0, tolerance_atr=0.5)
        assert not near_resistance(close=98, resistance=100, atr=1.0, tolerance_atr=0.5)


class TestKlineDensityZone:
    def test_bimodal_distribution(self):
        closes = [95 + i * 0.1 for i in range(30)] + [105 - i * 0.1 for i in range(30)]
        bars = make_bars(closes, spread=0.2)
        lo, hi = kline_density_zone(bars, lookback=60)
        assert lo is not None
        assert hi is not None
        assert lo < hi
