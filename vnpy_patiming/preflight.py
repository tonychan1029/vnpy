"""盘前自检：真实连通性检查（DB 可写、行情可达、Redis 可达）。

运行：python -m vnpy_patiming.preflight
任何硬性检查失败 -> 退出码 1（不跳过、不降级）。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def check_db() -> tuple[bool, str]:
    from .db import Database

    path = os.path.join(tempfile.gettempdir(), "patiming_preflight.db")
    try:
        db = Database(path)
        db.execute("SELECT 1")
        db.close()
        os.remove(path)
        return True, "DB writable"
    except Exception as exc:  # noqa: BLE001
        return False, f"DB failed: {exc}"


def check_market_data() -> tuple[bool, str]:
    from .adapters import AkshareOneMinuteFeed

    try:
        bars = AkshareOneMinuteFeed().fetch_1m("RB0", "SHFE")
        if len(bars) < 15:
            return False, f"行情条数不足: {len(bars)}"
        return True, f"行情 OK: {len(bars)} 根 1m, 最新 {bars[-1].datetime}"
    except Exception as exc:  # noqa: BLE001
        return False, f"行情失败: {exc}"


def check_redis() -> tuple[bool, str]:
    url = os.environ.get("PATIMING_REDIS_URL")
    if not url:
        return True, "Redis 未配置（跳过投递功能）"
    try:
        import redis

        conn = redis.Redis.from_url(url, decode_responses=True,
                                    protocol=2, socket_connect_timeout=3)
        return (bool(conn.ping()), "Redis OK")
    except Exception as exc:  # noqa: BLE001
        return False, f"Redis 失败: {exc}"


def check_token() -> tuple[bool, str]:
    token = os.environ.get("PATIMING_MCP_TOKEN", "")
    token_file = os.environ.get("PATIMING_MCP_TOKEN_FILE", "")
    if not token and token_file:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            return False, f"token file unreadable: {token_file}"
    return bool(token), "MCP token configured" if token else \
        "PATIMING_MCP_TOKEN/PATIMING_MCP_TOKEN_FILE not configured"


def check_live_poller() -> tuple[bool, str]:
    enabled = os.environ.get("PATIMING_ENABLE_POLLER", "").lower() in {
        "1", "true", "yes"
    }
    data_mode = os.environ.get(
        "PATIMING_DATA_MODE", "akshare_poll" if enabled else "ctp_tick"
    )
    if enabled and data_mode == "akshare_poll":
        return True, f"LIVE poller enabled ({data_mode})"
    return False, (
        "LIVE poller disabled; set PATIMING_ENABLE_POLLER=1 and "
        "PATIMING_DATA_MODE=akshare_poll"
    )


def check_trade_calendar() -> tuple[bool, str]:
    from .trading_calendar import refresh_trade_calendar

    dates = refresh_trade_calendar()
    if not dates:
        return False, "交易日历刷新失败"
    return True, f"交易日历 OK: {len(dates)} 个交易日"


def main() -> int:
    failures = 0
    for name, (ok, message) in (
        ("DB", check_db()),
        ("行情", check_market_data()),
        ("Redis", check_redis()),
        ("LIVE poller", check_live_poller()),
        ("交易日历", check_trade_calendar()),
    ):
        mark = "PASS" if ok else "FAIL"
        if not ok and name == "Redis":
            mark = "WARN"
        print(f"[{mark}] {name}: {message}")
        if not ok:
            failures += 1
    token_ok, token_message = check_token()
    print(f"[{'PASS' if token_ok else 'WARN'}] MCP token: "
          f"{token_message if not token_ok else '已配置'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
