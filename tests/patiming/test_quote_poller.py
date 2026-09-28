from datetime import datetime

from vnpy_patiming.quote_poller import QuotePoller, fetch_batch_quotes


def test_sina_latest_price_uses_field_eight(monkeypatch) -> None:
    class Response:
        status_code = 200
        content = (
            b'var hq_str_nf_RB0="RB,101500,3118.000,3119.000,3093.000,'
            b'0.000,3098.000,3099.000,3099.000,0.000,3111.000,483,439,'
            b'1649629.000,334660,SH,RB,2026-09-28,1";'
        )

        def raise_for_status(self) -> None:
            return

    monkeypatch.setattr("vnpy_patiming.quote_poller.httpx.get", lambda *_a, **_k: Response())
    quote = fetch_batch_quotes(["RB0"])["RB0"]
    assert quote["close"] == 3099.0


def test_quote_poller_builds_ohlc_from_latest_prices(monkeypatch) -> None:
    class Engine:
        def __init__(self) -> None:
            self.tasks = {"RB0.SHFE": None}
            self.bars = []

        def on_1m_bar(self, bar) -> None:
            self.bars.append(bar)

        def flush_due(self, now) -> None:
            return

    engine = Engine()
    poller = QuotePoller(engine, interval_s=1)
    quotes = {
        "100000": 3099.0,
        "100030": 3103.0,
        "100050": 3101.0,
        "100110": 3105.0,
    }

    def fake_fetch(_symbols):
        time_text = next(key for key, used in fake_fetch.used.items() if not used)
        fake_fetch.used[time_text] = True
        return {
            "RB0": {
                "time": time_text,
                "open": 3118.0,
                "high": 3119.0,
                "low": 3093.0,
                "close": quotes[time_text],
                "volume": 1000.0,
                "date": "2026-09-28",
            }
        }

    fake_fetch.used = {key: False for key in quotes}
    monkeypatch.setattr("vnpy_patiming.quote_poller.fetch_batch_quotes", fake_fetch)
    for _ in range(4):
        poller.poll_once()

    assert len(engine.bars) == 1
    bar = engine.bars[0]
    assert bar.datetime == datetime(2026, 9, 28, 10, 0)
    assert bar.open_price == 3099.0
    assert bar.high_price == 3103.0
    assert bar.low_price == 3099.0
    assert bar.close_price == 3101.0
    assert bar.volume == 0.0
