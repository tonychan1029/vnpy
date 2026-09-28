from datetime import datetime

from vnpy_patiming.market import is_trading_time, trading_minutes_between


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
