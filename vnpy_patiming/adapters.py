"""真实行情数据适配（spec：预热数据源）。

AkShare/新浪 1m 真实K线 -> 引擎预热与逐根喂入。
这是真实数据直连实现，不含 CTP->AkShare 兜底订阅机制；
CTP 实时链路由 vnpy 网关在 App 模式接入（app.py）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

from .market import canonical_symbol

class AkshareOneMinuteFeed:
    def __init__(self) -> None:
        import akshare as ak

        self._ak = ak

    def fetch_minutes(self, symbol: str, exchange: str = "SHFE",
                      period: str = "1") -> list[BarData]:
        """period: '1'/'15'/'30'/'60'，新浪分钟线（真实行情）。"""
        base = symbol.split(".")[0]
        exch = exchange.split(".")[-1] if "." in exchange else exchange
        code = canonical_symbol(base, exch)
        sina_symbol = base.upper()
        interval = Interval.MINUTE if period == "1" else None
        frame = self._ak.futures_zh_minute_sina(symbol=sina_symbol, period=period)
        bars: list[BarData] = []
        for row in frame.to_dict("records"):
            interval_value = interval
            if interval_value is None:
                interval_value = Interval.HOUR if period == "60" else Interval.MINUTE
            bars.append(BarData(
                symbol=code,
                exchange=Exchange(exchange),
                datetime=datetime.strptime(str(row["datetime"])[:19], "%Y-%m-%d %H:%M:%S"),
                gateway_name="AKSHARE_REAL",
                interval=interval_value,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row.get("volume", 0) or 0),
            ))
        return bars

    def fetch_1m(self, symbol: str, exchange: str = "SHFE") -> list[BarData]:
        """symbol 支持连续合约代码（RB0）或全代码（rb2501.SHFE）。"""
        return self.fetch_minutes(symbol, exchange, period="1")


def warmup_engine(engine, bars: list[BarData]) -> int:
    """按时间序喂入真实K线完成预热；返回处理根数（含 flush 兜底完成）。"""
    for bar in bars:
        engine.on_1m_bar(bar)
    if bars:
        engine.flush_due(bars[-1].datetime + timedelta(minutes=1))
    return len(bars)
