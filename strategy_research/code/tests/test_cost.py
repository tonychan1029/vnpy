"""cost.py 单一成本实现回归测试（阶段0-2）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.cost import (  # noqa: E402
    COMMISSION_PER_SIDE, DEFAULT_MARGIN_RATE, TICK_SIZE, cost_return,
    net_of_cost)


def test_rb_known_value():
    # RB@3500: 佣金 0.12*0.0003*2=7.2e-5；滑点 2*1/3500≈5.714e-4
    c = cost_return("RB", 3500.0)
    expect = 0.12 * COMMISSION_PER_SIDE * 2 + 2 * TICK_SIZE["RB"] / 3500.0
    assert abs(c - expect) < 1e-12
    assert 0.0005 < c < 0.0008


def test_unknown_symbol_uses_defaults():
    c1 = cost_return("ZZ", 1000.0)
    c2 = cost_return("ZZ", 1000.0)
    assert c1 == c2 == DEFAULT_MARGIN_RATE * COMMISSION_PER_SIDE * 2 + 0.0006


def test_slip_decays_with_price():
    assert cost_return("RB", 5000.0) < cost_return("RB", 3000.0)


def test_net_of_cost_direction():
    net = net_of_cost("RB", 3500.0, 0.01)
    assert 0 < net < 0.01
    assert net_of_cost("RB", 3500.0, -0.01) < -0.01


def test_price_guard():
    try:
        cost_return("RB", 0.0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
