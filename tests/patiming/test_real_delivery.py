"""真实 Redis Stream 投递验证（本机实例，protocol=2）。"""

from conftest import feed_bars, flush_window, make_bar, make_engine, submit_ok
from vnpy_patiming.delivery import make_redis_stream_handler


def test_redis_stream_delivery(tmp_path, clock):
    import redis

    reader = redis.Redis.from_url("redis://127.0.0.1:6379/0",
                                  decode_responses=True, protocol=2)
    reader.delete("patiming:test:delivery")
    handler = make_redis_stream_handler("redis://127.0.0.1:6379/0",
                                        "patiming:test:delivery")
    handler.ping()

    eng = make_engine(tmp_path, clock)
    eng.register_delivery_handler(handler)
    submit_ok(eng, iid="INS-1", key_levels={"prior_high": 100.0})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.4, 101.0, 99.0, 100.6))
    flush_window(eng, clock)
    task = eng.tasks[("rb2501.SHFE", "1m")]
    alert = next(a for a in task.alerts.values()
                 if a.signal_id == "BREAKOUT_KEY_LEVEL")
    eng.deliver_pending()

    import json

    rows = eng.db.query(
        "SELECT payload_json FROM alert_outbox WHERE alert_id=? ORDER BY id",
        (alert.alert_id,))
    entries = reader.xrange("patiming:test:delivery")
    payloads = [json.loads(e[1]["payload"]) for e in entries]
    ids = [p["payload"]["event_id"] for p in payloads]
    assert alert.alert_id in ids
    assert len(rows) == len([i for i in ids if i == alert.alert_id])
