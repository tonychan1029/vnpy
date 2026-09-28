from datetime import datetime

import pytest

from vnpy.trader.constant import Exchange
from vnpy.trader.object import BarData

from vnpy_patiming import market
from vnpy_patiming.market import BarSynthesizer, is_trading_time, \
    trading_minutes_between, window_index


@pytest.fixture(autouse=True)
def weekday_calendar(monkeypatch):
    monkeypatch.setattr(market, "is_trade_date", lambda value: value.weekday() < 5)


def _bar(hour: int, minute: int) -> BarData:
    return BarData(
        symbol="ss0", exchange=Exchange.SHFE,
        datetime=datetime(2026, 9, 28, hour, minute),
        gateway_name="TEST", open_price=1, high_price=1,
        low_price=1, close_price=1, volume=1,
    )


def test_commodity_lunch_break_is_not_staleness() -> None:
    traded = trading_minutes_between(
        datetime(2026, 9, 28, 11, 30),
        datetime(2026, 9, 28, 13, 31),
        "SHFE", "SS0",
    )
    assert traded == 1.0


def test_post_night_break_is_not_staleness() -> None:
    traded = trading_minutes_between(
        datetime(2026, 9, 24, 23, 0),
        datetime(2026, 9, 25, 9, 1),
        "CZCE", "FG0",
    )
    assert traded == 1.0


def test_stock_index_afternoon_open_is_adjacent() -> None:
    traded = trading_minutes_between(
        datetime(2026, 9, 28, 11, 30),
        datetime(2026, 9, 28, 13, 1),
        "CFFEX", "IF0",
    )
    assert traded == 1.0


def test_trading_time_boundaries() -> None:
    assert is_trading_time(datetime(2026, 9, 28, 10, 14, 59), "SHFE", "NI0")
    assert not is_trading_time(datetime(2026, 9, 28, 10, 15), "SHFE", "NI0")
    assert is_trading_time(datetime(2026, 9, 28, 13, 30), "CZCE", "FG0")
    assert not is_trading_time(datetime(2026, 9, 28, 13, 0), "CZCE", "FG0")


def test_sixty_minute_window_requires_expected_trading_minutes() -> None:
    synth = BarSynthesizer("60m")
    assert synth.update(_bar(13, 0)) is None
    # A restart at 13:00 saw only part of the 13:00-14:00 execution window.
    assert synth.update(_bar(14, 0)) is None
    assert synth._idx == window_index(datetime(2026, 9, 28, 14, 0), 60)
