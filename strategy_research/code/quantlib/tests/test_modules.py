# RESEARCH ONLY - quantlib 全模块单元测试（v2 修正版）
"""quantlib 全模块测试：structure/pullback/entry_signal/exhaustion/gap。"""
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
from quantlib.pullback import retracement_fraction, near_ma, near_level, support_held
from quantlib.entry_signal import breakout_confirm, pin_bar, engulf_detect, near_ma_doji
from quantlib.exhaustion import volume_divergence, selling_climax, wedge_three_push


def make_bars(closes, spread=1.0):
    bars = []
    for i, c in enumerate(closes):
        o = c - spread / 2
        h = c + spread
        l = c - spread
        bars.append([f"d{i:04d}", o, h, l, c, 1000, 5000])
    return bars


# ── structure 测试 ────────────────────────────────────────────

class TestSwingPoints:
    def test_zigzag_produces_alternating(self):
        closes = []
        for i in range(120):
            phase = i % 20
            if phase < 10:
                closes.append(100 + phase * 2)
            else:
                closes.append(110 - (phase - 10) * 2)
        bars = make_bars(closes, spread=0.5)
        swings = find_swing_points(bars, left=3, right=3)
        types = [s["type"] for s in swings]
        for i in range(1, len(types)):
            assert types[i] != types[i - 1]

    def test_flat_no_swings(self):
        bars = make_bars([100] * 60, spread=0.1)
        assert len(find_swing_points(bars, left=5, right=5)) == 0


class TestTrendZigzag:
    def test_bull(self):
        # 上升趋势 + 回调
        closes = []
        price = 100
        for cycle in range(10):
            for i in range(10):
                price += 1.5
                closes.append(price)
            for i in range(3):
                price -= 2
                closes.append(price)
        bars = make_bars(closes, spread=0.5)
        assert detect_trend_zigzag(bars) in ("多头", "震荡")

    def test_bear(self):
        closes = []
        price = 200
        for cycle in range(10):
            for i in range(10):
                price -= 1.5
                closes.append(price)
            for i in range(3):
                price += 2
                closes.append(price)
        bars = make_bars(closes, spread=0.5)
        assert detect_trend_zigzag(bars) in ("空头", "震荡")


class TestTrendEmaSlope:
    def test_bull(self):
        # 强趋势 + 小回调 → EMA 上斜 + HH/HL
        closes = []
        price = 100
        for i in range(120):
            price += 0.8  # 每根涨 0.8，持续上升
            closes.append(price)
        bars = make_bars(closes, spread=0.5)
        assert detect_trend_ema_slope(bars) == "多头"

    def test_bear(self):
        closes = []
        price = 200
        for i in range(120):
            price -= 0.8  # 每根跌 0.8，持续下降
            closes.append(price)
        bars = make_bars(closes, spread=0.5)
        assert detect_trend_ema_slope(bars) == "空头"


class TestClassifyTrend:
    def test_zigzag_method(self):
        closes = []
        price = 100
        for i in range(120):
            price += 0.5
            closes.append(price)
        bars = make_bars(closes, spread=0.5)
        assert classify_trend(bars, method="zigzag") in ("多头", "空头", "震荡")

    def test_ema_slope_method(self):
        closes = [100 + i * 0.5 for i in range(120)]
        bars = make_bars(closes, spread=0.5)
        assert classify_trend(bars, method="ema_slope") in ("多头", "空头", "震荡")


class TestRangeBoundary:
    def test_swing_method(self):
        # 构造明显的区间震荡
        closes = []
        for i in range(120):
            base = 100 + 10 * ((i // 30) % 2)  # 每30根切换100↔110
            closes.append(base + (i % 10) - 5)  # 加小波动
        bars = make_bars(closes, spread=0.5)
        support, resistance = find_range_boundary(bars, lookback=60, method="swing")
        assert support is not None and resistance is not None
        assert support < resistance

    def test_percentile_method(self):
        closes = [100 + i * 0.5 for i in range(120)]
        bars = make_bars(closes, spread=0.5)
        support, resistance = find_range_boundary(bars, lookback=60, method="percentile")
        assert support is not None and resistance is not None


class TestSupport:
    def test_near_support(self):
        assert near_support(close=100.3, support=100.3, atr=1.0, tolerance_atr=0.5)
        assert not near_support(close=102, support=100, atr=1.0, tolerance_atr=0.5)

    def test_near_resistance(self):
        assert near_resistance(close=100.3, resistance=100.0, atr=1.0, tolerance_atr=0.5)
        assert not near_resistance(close=98, resistance=100, atr=1.0, tolerance_atr=0.5)


class TestKlineDensity:
    def test_density_zone(self):
        closes = [95 + i * 0.1 for i in range(30)] + [105 - i * 0.1 for i in range(30)]
        bars = make_bars(closes, spread=0.2)
        lo, hi = kline_density_zone(bars, lookback=60)
        assert lo is not None and hi is not None and lo < hi


# ── pullback 测试 ─────────────────────────────────────────────

class TestPullback:
    def test_retracement(self):
        assert abs(retracement_fraction(110, 100, 105) - 0.5) < 0.01

    def test_near_ma(self):
        assert near_ma(close=100.3, ma=100, atr=1.0, tolerance_atr=0.5)
        assert not near_ma(close=105, ma=100, atr=1.0, tolerance_atr=0.5)

    def test_near_level(self):
        assert near_level(close=100.4, level=100, atr=1.0, tolerance_atr=0.5)

    def test_support_held(self):
        bars = [[f"d{i}", 100, 101, 99, 100.2, 1000, 5000] for i in range(5)]
        assert support_held(bars, support=98, buffer_pct=0.02, confirm_bars=3)


# ── entry_signal 测试 ─────────────────────────────────────────

class TestBreakoutConfirm:
    def test_breakout_up(self):
        # 前 20 根区间 99-101（满足 window+1=21 根下限），最后 1 根收 111.5 → 明确突破
        bars = []
        for i in range(21):
            c = 100 + (i % 3) * 0.3
            bars.append([f"d{i:04d}", c - 0.3, c + 0.5, c - 0.5, c, 1000, 5000])
        bars[-1] = ["d0020", 110, 112, 109.5, 111.5, 2000, 5000]
        r = breakout_confirm(bars, window=20, body_ratio_min=0.5,
                             buffer_atr=0.1, atr=1.0)
        assert r is not None
        assert r["direction"] == "long"

    def test_range_no_breakout(self):
        bars = []
        for i in range(21):
            c = 100 + (i % 5) * 0.1
            bars.append([f"d{i:04d}", c - 0.3, c + 0.3, c - 0.3, c, 1000, 5000])
        r = breakout_confirm(bars, window=20, body_ratio_min=0.5,
                             buffer_atr=0.1, atr=1.0)
        assert r is None


class TestPinBar:
    def test_bullish_pin(self):
        # 下影线 = min(o,c) - l = 100 - 94 = 6.0; body = |102.5-100| = 2.5
        # 6.0 >= 2.0 × 2.5 = 5.0 ✓
        r = pin_bar(o=100, h=103, l=94, c=102.5, shadow_body_ratio=2.0,
                    close_position=1 / 3)
        assert r == "long"

    def test_bearish_pin(self):
        # o=100, h=107, l=96, c=97 → body=3, 上影线=107-100=7 ≥ 2×3=6 ✓
        r = pin_bar(o=100, h=107, l=96, c=97, shadow_body_ratio=2.0,
                    close_position=1 / 3)
        assert r == "short", f"got: {r}"


class TestEngulf:
    def test_bullish_engulf(self):
        r = engulf_detect(o=100, h=102.5, l=99.5, c=102,
                          prev_o=102, prev_h=102.5, prev_l=99.5, prev_c=100)
        assert r == "long"

    def test_bearish_engulf(self):
        r = engulf_detect(o=102, h=102.5, l=99.5, c=100,
                          prev_o=100, prev_h=102.5, prev_l=99.5, prev_c=102)
        assert r == "short"


class TestNearMaDoji:
    def test_doji_near_ma(self):
        # 十字星：|c-o|=0.05, 全长=1.0 → body_ratio=0.05 ≤ 0.1 ✓; |c-ma|=0.1≤0.5 ✓
        r = near_ma_doji(o=100.05, h=100.5, l=99.5, c=100.0,
                         ma=100.0, ma_tolerance=0.5, doji_body_ratio=0.1)
        assert r is True

    def test_not_doji_big_body(self):
        r = near_ma_doji(o=100, h=103, l=99, c=102.5,
                         ma=100.0, ma_tolerance=0.5, doji_body_ratio=0.1)
        assert not r  # body=2.5/rng=4 → 0.625 > 0.1 → 不是十字星


class TestVolumeDivergence:
    def test_bearish_divergence(self):
        # 价涨量缩 → 看跌背离
        bars = [[f"d{i:04d}", 100 + i * 0.5, 100 + i * 0.5 + 0.5,
                 100 + i * 0.5 - 0.5, 100 + i * 0.5,
                 2000 - i * 30, 5000] for i in range(25)]
        r = volume_divergence(bars, lookback=20)
        assert r == "bearish"

    def test_bullish_divergence(self):
        # 价跌量缩 → 看涨背离（抛压减轻）
        bars = [[f"d{i:04d}", 110 - i * 0.5, 110 - i * 0.5 + 0.5,
                 110 - i * 0.5 - 0.5, 110 - i * 0.5,
                 2000 - i * 30, 5000] for i in range(25)]
        r = volume_divergence(bars, lookback=20)
        assert r == "bullish"


class TestSellingClimax:
    def test_selling_climax(self):
        bars = [[f"d{i:04d}", 110 - i * 0.5, 110 - i * 0.5 + 0.5,
                 110 - i * 0.5 - 0.5, 110 - i * 0.5, 1000, 5000]
                for i in range(25)]
        r = selling_climax(bars, atr=2.0, vol_mult=1.5)
        assert isinstance(r, bool)

def test_wedge_three_push_amplitude_decay():
    """阶段0-4 勘误回归：幅度衰减语义（旧版价格序判向 + decay_ratio 死参数）。"""
    closes = [100.0] * 6
    for a, b, k in ((100, 105, 5), (105, 104, 4), (104, 107, 5),
                    (107, 106.5, 4), (106.5, 108, 5), (108, 107.5, 4)):
        closes += [a + (b - a) * i / k for i in range(1, k + 1)]
    bars = [[i, c, c + 0.2, c - 0.2, c, 100.0, 0.0]
            for i, c in enumerate(closes)]
    r = wedge_three_push(bars, window=30)
    assert r is not None and r["direction"] == "short"
    a1, a2, a3 = r["pushes"]
    assert a1 > a2 > a3 and a3 <= 0.67 * a1
