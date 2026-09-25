"""Outbox 投递实现（spec 5.5）：Redis Stream 发布器。

用法：engine.register_delivery_handler(make_redis_stream_handler(url, stream))
语义：at-least-once，下游按 event_id 幂等消费。
"""

from __future__ import annotations

import json


def make_redis_stream_handler(url: str, stream: str, max_len: int | None = 100000,
                              protocol: int = 2):
    import redis

    conn = redis.Redis.from_url(url, decode_responses=True, protocol=protocol)

    def deliver(event: dict) -> None:
        conn.xadd(stream, {"payload": json.dumps(event, ensure_ascii=False)})

    deliver.ping = conn.ping  # type: ignore[attr-defined]
    return deliver
