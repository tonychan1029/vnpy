"""China futures trading calendar with a local, self-refreshing cache."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)
CHINA_TZ = timezone(timedelta(hours=8))
_DEFAULT_CACHE = Path(tempfile.gettempdir()) / "patiming_trading_calendar.json"
_lock = threading.RLock()
_refreshing = False
_cache: set[date] | None = None
_loaded_at: datetime | None = None
_last_attempt: datetime | None = None


def _cache_path() -> Path:
    return Path(
        os.environ.get(
            "PATIMING_TRADE_CALENDAR_CACHE",
            str(_DEFAULT_CACHE),
        )
    )


def _ttl_days() -> int:
    return max(1, int(os.environ.get("PATIMING_TRADE_CALENDAR_TTL_DAYS", "7")))


def _refresh_enabled() -> bool:
    return os.environ.get(
        "PATIMING_TRADE_CALENDAR_REFRESH", "1"
    ).lower() in {"1", "true", "yes"}


def _china_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(CHINA_TZ)
        return value.date()
    return value


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _read_cache(path: Path) -> tuple[set[date], datetime | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dates = {_parse_date(item) for item in payload["trade_dates"]}
        loaded_at = datetime.fromisoformat(payload["fetched_at"])
        if loaded_at.tzinfo is None:
            loaded_at = loaded_at.replace(tzinfo=timezone.utc)
        return dates, loaded_at
    except Exception as exc:
        if path.exists():
            logger.warning("Trading calendar cache invalid: %s", exc)
        return set(), None


def _write_cache(path: Path, dates: set[date], loaded_at: datetime) -> None:
    payload = {
        "source": "akshare.tool_trade_date_hist_sina",
        "fetched_at": loaded_at.isoformat(),
        "trade_dates": sorted(item.isoformat() for item in dates),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o666)


def _refresh_cache(ak: Any = None, path: Path | None = None) -> set[date] | None:
    target = path or _cache_path()
    try:
        if ak is None:
            import akshare as akshare_mod

            ak = akshare_mod
        table = ak.tool_trade_date_hist_sina()
        if table is None or getattr(table, "empty", False):
            raise ValueError("empty trading calendar table")
        if "trade_date" not in getattr(table, "columns", []):
            raise ValueError("trade_date column missing")
        columns = getattr(table, "columns", None)
        if columns is not None and "trade_date" in columns:
            try:
                values = table["trade_date"]
            except TypeError:
                values = getattr(table, "trade_date")
        else:
            values = getattr(table, "trade_date")
        dates = {_parse_date(item) for item in (
            values.tolist() if hasattr(values, "tolist") else values
        )}
        if not dates:
            raise ValueError("empty trading calendar")
        loaded_at = datetime.now(timezone.utc)
        _write_cache(target, dates, loaded_at)
        with _lock:
            global _cache, _loaded_at
            _cache = dates
            _loaded_at = loaded_at
        return dates
    except Exception as exc:
        logger.warning("Trading calendar refresh failed: %s", exc)
        return None
    finally:
        with _lock:
            global _refreshing
            _refreshing = False


def refresh_trade_calendar(ak: Any = None) -> set[date] | None:
    """Refresh immediately; used by preflight and by the background worker."""
    return _refresh_cache(ak)


def reset_calendar_cache() -> None:
    """Reset process state; tests and deployment checks may use this."""
    global _cache, _loaded_at, _last_attempt, _refreshing
    with _lock:
        _cache = None
        _loaded_at = None
        _last_attempt = None
        _refreshing = False


def get_trade_dates(*, allow_refresh: bool = True) -> set[date] | None:
    """Return cached dates, or None when no reliable calendar is available.

    A stale cache is still returned while a background refresh is running, so
    runtime gating never blocks on AkShare. Weekdays are the fallback only when
    no cache has ever been produced.
    """
    global _cache, _loaded_at, _last_attempt, _refreshing
    path = _cache_path()
    now = datetime.now(timezone.utc)
    with _lock:
        if _cache is None:
            dates, loaded_at = _read_cache(path)
            _cache = dates if loaded_at else None
            _loaded_at = loaded_at

    with _lock:
        fresh = bool(
            _loaded_at
            and now - _loaded_at <= timedelta(days=_ttl_days())
        )
        result = set(_cache) if _cache is not None else None
        needs_refresh = _cache is None or not fresh
        can_retry = (
            _last_attempt is None
            or now - _last_attempt >= timedelta(hours=1)
        )
        should_refresh = bool(
            allow_refresh
            and _refresh_enabled()
            and not _refreshing
            and needs_refresh
            and can_retry
        )
        if should_refresh:
            _refreshing = True
            _last_attempt = now

    if should_refresh:
        threading.Thread(
            target=_refresh_cache,
            name="patiming-trade-calendar-refresh",
            daemon=True,
        ).start()
    return result


def is_trade_date(value: datetime | date) -> bool:
    """Whether the calendar date is a China exchange trading date."""
    trade_date = _parse_date(value) if isinstance(value, str) else _china_date(value)
    dates = get_trade_dates()
    if dates is None:
        return trade_date.weekday() < 5
    return trade_date in dates
