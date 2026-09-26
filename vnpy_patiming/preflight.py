"""盘前自检：真实连通性检查（DB 可写、行情可达、Redis 可达）。

运行：python -m vnpy_patiming.preflight
任何硬性检查失败 -> 退出码 1（不跳过、不降级）。
"""

from __future__ import annotations

import os
import sys
import tempfile


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


def main() -> int:
    failures = 0
    for name, (ok, message) in (
        ("DB", check_db()),
        ("行情", check_market_data()),
        ("Redis", check_redis()),
    ):
        mark = "PASS" if ok else "FAIL"
        if not ok and name == "Redis":
            mark = "WARN"
        print(f"[{mark}] {name}: {message}")
        if not ok:
            failures += 1
    token = os.environ.get("PATIMING_MCP_TOKEN")
    print(f"[{'PASS' if token else 'WARN'}] MCP token: "
          f"{'已配置' if token else '未配置 PATIMING_MCP_TOKEN（写入面不可用）'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
