import json
from datetime import date

import pytest

from vnpy_patiming import trading_calendar


@pytest.fixture()
def calendar_cache(tmp_path, monkeypatch):
    path = tmp_path / "trading-calendar.json"
    monkeypatch.setenv("PATIMING_TRADE_CALENDAR_CACHE", str(path))
    monkeypatch.setenv("PATIMING_TRADE_CALENDAR_REFRESH", "0")
    trading_calendar.reset_calendar_cache()
    yield path
    trading_calendar.reset_calendar_cache()


def test_refresh_trade_calendar_writes_cache(calendar_cache):
    class FakeTable:
        empty = False
        columns = ["trade_date"]

        class _Column:
            @staticmethod
            def tolist():
                return ["2026-09-28", "2026-09-29"]

        trade_date = _Column()

    class FakeAk:
        @staticmethod
        def tool_trade_date_hist_sina():
            return FakeTable

    dates = trading_calendar.refresh_trade_calendar(FakeAk())

    assert dates == {date(2026, 9, 28), date(2026, 9, 29)}
    payload = json.loads(calendar_cache.read_text(encoding="utf-8"))
    assert payload["trade_dates"] == ["2026-09-28", "2026-09-29"]
    assert trading_calendar.is_trade_date("2026-09-28") is True
    assert trading_calendar.is_trade_date("2026-09-30") is False


def test_missing_calendar_falls_back_to_weekday(calendar_cache):
    import datetime as dt

    assert trading_calendar.is_trade_date(dt.date(2026, 9, 28)) is True
    assert trading_calendar.is_trade_date(dt.date(2026, 9, 26)) is False
