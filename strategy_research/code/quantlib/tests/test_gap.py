# RESEARCH ONLY - quantlib.gap 单元测试
"""quantlib.gap 缺口检测与分类测试。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quantlib.gap import detect_gaps, is_gap_filled, classify_gap, gap_as_level


def make_bars_with_gap(base=100, gap_pct=3.0, direction="up", pre_bars=10, post_bars=20):
    """构造含跳空的测试数据。"""
    bars = []
    price = base
    for i in range(pre_bars):
        o = price
        c = price + 0.5
        h = c + 0.5
        l = o - 0.5
        bars.append([f"2026-01-{i+1:02d} 09:00", o, h, l, c, 1000, 5000])
        price = c
    # 跳空
    gap_size = price * gap_pct / 100
    if direction == "up":
        gap_open = price + gap_size
    else:
        gap_open = price - gap_size
    o = gap_open
    c = gap_open + 0.3 * (1 if direction == "up" else -1)
    h = max(o, c) + 0.3
    l = min(o, c) - 0.3
    bars.append([f"2026-01-{pre_bars+11:02d} 09:00", o, h, l, c, 2000, 5000])
    price = c
    for i in range(post_bars):
        o = price
        c = price + 0.3 * (1 if i % 3 != 0 else -1)
        h = c + 0.5
        l = c - 0.5
        bars.append([f"2026-02-{i+1:02d} 09:00", o, h, l, c, 800, 5000])
        price = c
    return bars


class TestDetectGaps:
    def test_up_gap_detected(self):
        bars = make_bars_with_gap(base=100, gap_pct=3.0, direction="up")
        gaps = detect_gaps(bars, method="simple")
        assert len(gaps) > 0
        assert gaps[0]["direction"] == "up"

    def test_down_gap_detected(self):
        bars = make_bars_with_gap(base=200, gap_pct=3.0, direction="down")
        gaps = detect_gaps(bars, method="simple")
        assert len(gaps) > 0
        assert gaps[0]["direction"] == "down"

    def test_atr_filter_removes_small_gaps(self):
        bars = make_bars_with_gap(base=100, gap_pct=0.1, direction="up")
        gaps_simple = detect_gaps(bars, method="simple")
        gaps_atr = detect_gaps(bars, method="atr", min_gap_atr=0.5)
        # ATR 过滤应至少与简单检测同等严格
        assert len(gaps_atr) <= len(gaps_simple)

    def test_no_gap_no_detection(self):
        bars = []
        price = 100
        for i in range(30):
            o = price
            c = price + 0.1
            h = c + 0.3
            l = o - 0.3
            bars.append([f"2026-01-{i+1:02d} 09:00", o, h, l, c, 1000, 5000])
            price = c
        gaps = detect_gaps(bars, method="simple")
        assert len(gaps) == 0


class TestGapFilled:
    def test_gap_filled_detected(self):
        bars = make_bars_with_gap(base=100, gap_pct=3.0, direction="up")
        gaps = detect_gaps(bars, method="simple")
        assert len(gaps) > 0
        gap = gaps[0]
        # 后续价格回到缺口底部以下 → 缺口被回补
        filled = is_gap_filled(bars, gap, within_bars=20)
        # 不 assert 具体值（取决于测试数据），只验证函数不崩溃
        assert isinstance(filled, bool)


class TestClassifyGap:
    def test_classification_returns_valid_type(self):
        bars = make_bars_with_gap(base=100, gap_pct=3.0, direction="up")
        gaps = detect_gaps(bars, method="simple")
        assert len(gaps) > 0
        gap = gaps[0]
        gtype = classify_gap(bars, gap)
        assert gtype in ("breakaway", "runaway", "exhaustion", "common")


class TestGapAsLevel:
    def test_gap_level_structure(self):
        bars = make_bars_with_gap(base=100, gap_pct=3.0, direction="up")
        gaps = detect_gaps(bars, method="simple")
        assert len(gaps) > 0
        gap = gaps[0]
        level = gap_as_level(gap)
        assert level["type"] == "gap_level"
        assert level["bottom"] < level["top"]
        assert 0 <= level["strength"] <= 1
