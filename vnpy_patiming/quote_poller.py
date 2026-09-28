"""LIVE 数据面主路径（D6）：新浪批量快照 -> 本地 1m 合成 -> 引擎。

全池每轮 1~2 次 HTTP；REST 分钟拉取降级为预热/缺口修复；
T口 tick 订阅为末级兜底（D7，经 tick_fallback_hooks 接线）。
"""

from __future__ import annotations

import re
import threading
import time
import logging
from datetime import datetime

import httpx

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData


URL = "https://hq.sinajs.cn/list={lists}"
HEADERS = {"Referer": "https://finance.sina.com.cn"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
logger = logging.getLogger(__name__)


def fetch_batch_quotes(sina_symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for start in range(0, len(sina_symbols), 50):
        chunk = sina_symbols[start : start + 50]
        resp = httpx.get(URL.format(lists=",".join(f"nf_{s}" for s in chunk)),
                         headers=HEADERS, timeout=5.0)
        resp.raise_for_status()
        text = resp.content.decode("gbk", errors="ignore")
        for line in text.splitlines():
            m = re.match(r'var hq_str_nf_(\w+)="(.*)";?', line.strip())
            if not m:
                continue
            fields = m.group(2).split(",")
            if len(fields) < 18:
                continue
            # Sina futures snapshots expose the latest price in field 8.
            # Field 5 can be zero for continuous contracts during trading.
            last_price = float(fields[8] or fields[7] or fields[6] or fields[5])
            out[m.group(1)] = {"time": fields[1], "open": float(fields[2]),
                "high": float(fields[3]), "low": float(fields[4]),
                "close": last_price, "volume": float(fields[14]),
                "date": next((f for f in fields if DATE_RE.match(f)), "")}
    return out


def _parse_quote_datetime(date_text: str, time_text: str) -> datetime:
    time_format = "%H:%M:%S" if ":" in time_text else "%H%M%S"
    return datetime.strptime(
        f"{date_text} {time_text}",
        f"%Y-%m-%d {time_format}",
    )


class QuotePoller:
    """批量快照 -> 本地 1m 合成 -> engine.on_1m_bar。"""

    def __init__(self, engine, interval_s: float = 5.0) -> None:
        self.engine = engine
        self.interval_s = interval_s
        self._acc: dict[str, dict] = {}
        self._running = False

    def poll_once(self) -> int:
        now = datetime.now()
        symbols_by_vt = {}
        for (symbol, _tf) in self.engine.tasks:
            base, exchange = symbol.rsplit(".", 1)
            symbols_by_vt[symbol] = (base.upper(), exchange, symbol, base)
        symbols = list(symbols_by_vt.values())
        if not symbols:
            return 0
        quotes = fetch_batch_quotes([s for s, _e, _v, _c in symbols])
        emitted = 0
        for base, exch, vt, canonical_base in symbols:
            q = quotes.get(base)
            if not q or not q["date"]:
                continue
            dt = _parse_quote_datetime(q["date"], str(q["time"]))
            minute = dt.replace(second=0, microsecond=0)
            acc = self._acc.get(vt)
            if acc and acc["minute"] != minute:
                self.engine.on_1m_bar(BarData(
                    symbol=canonical_base, exchange=Exchange(exch),
                    datetime=acc["minute"],
                    gateway_name="SINA_SNAPSHOT",
                    open_price=acc["o"], high_price=acc["h"], low_price=acc["l"],
                    close_price=acc["c"], volume=acc["v"]))
                emitted += 1
                acc = None
            if acc is None:
                last = float(q["close"])
                self._acc[vt] = {"minute": minute, "o": last, "h": last,
                                 "l": last, "c": last, "v": 0.0,
                                 "v0": q["volume"]}
            else:
                last = float(q["close"])
                acc["h"] = max(acc["h"], last)
                acc["l"] = min(acc["l"], last)
                acc["c"] = q["close"]
                acc["v"] = max(0.0, q["volume"] - acc["v0"])
        self.engine.flush_due(now)
        return emitted

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        def loop() -> None:
            while self._running:
                try:
                    self.poll_once()
                except Exception:
                    logger.exception("quote poll failed")
                time.sleep(self.interval_s)

        threading.Thread(target=loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
