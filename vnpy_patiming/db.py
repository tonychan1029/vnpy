"""SQLite persistence. The engine process is the only writer (spec 3.5)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS timing_instruction (
    source              TEXT NOT NULL,
    instruction_id      TEXT NOT NULL,
    producer_revision   INTEGER NOT NULL,
    desired_status      TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    selection_timeframe TEXT NOT NULL,
    exec_timeframe      TEXT NOT NULL,
    context_tag         TEXT,
    signal_categories   TEXT,
    direction           TEXT,
    key_levels          TEXT,
    params              TEXT,
    priority            INTEGER,
    reason_code         TEXT NOT NULL,
    reason_note         TEXT NOT NULL,
    valid_bars          INTEGER,
    valid_until         TEXT,
    content_hash        TEXT,
    status              TEXT NOT NULL,
    feedback            TEXT,
    effective_from      TEXT,
    anchor_bar          TEXT,
    expires_bar         TEXT,
    remaining_bars      INTEGER,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (source, instruction_id)
);
CREATE TABLE IF NOT EXISTS timing_instruction_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    instruction_id TEXT NOT NULL,
    producer_revision INTEGER,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    actor TEXT NOT NULL,
    payload_snapshot TEXT,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timing_alert_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_lifecycle TEXT,
    to_lifecycle TEXT,
    instruction_keys TEXT,
    payload_snapshot TEXT,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON alert_outbox(delivery_status, next_retry_at, id);
CREATE INDEX IF NOT EXISTS idx_instruction_status
    ON timing_instruction(status);
CREATE INDEX IF NOT EXISTS idx_alert_event_alert
    ON timing_alert_event(alert_id, id);
CREATE TABLE IF NOT EXISTS market_bars (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    interval TEXT NOT NULL,
    dt TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, exchange, interval, dt)
);
"""

def now_str(clock) -> str:
    return clock().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class Database:
    """Thin sqlite3 DAO. All writes happen inside the engine process/lock."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.conn.execute(sql, params)

    def commit(self) -> None:
        self.conn.commit()

    def save_bars(self, rows: list[dict]) -> int:
        new = 0
        for r in rows:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO market_bars VALUES (?,?,?,?,?,?,?,?,?)",
                (r["symbol"], r["exchange"], r["interval"], r["dt"],
                 r["open"], r["high"], r["low"], r["close"], r["volume"]),
            )
            new += cur.rowcount
        self.commit()
        return new

    def load_bars(self, symbol: str, exchange: str, interval: str) -> list[dict]:
        return self.query(
            "SELECT * FROM market_bars WHERE symbol=? AND exchange=? AND interval=? "
            "ORDER BY dt", (symbol, exchange, interval),
        )

    def atomic(self) -> sqlite3.Connection:
        return self.conn

    def save_bars(self, rows: list[dict]) -> int:
        new = 0
        for r in rows:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO market_bars VALUES (?,?,?,?,?,?,?,?,?)",
                (r["symbol"], r["exchange"], r["interval"], r["dt"],
                 r["open"], r["high"], r["low"], r["close"], r["volume"]),
            )
            new += cur.rowcount
        self.commit()
        return new

    def load_bars(self, symbol: str, exchange: str, interval: str) -> list[dict]:
        return self.query(
            "SELECT * FROM market_bars WHERE symbol=? AND exchange=? AND interval=? "
            "ORDER BY dt", (symbol, exchange, interval),
        )

    # ---------------- instructions ----------------

    def fetch_instruction(self, source: str, instruction_id: str) -> dict | None:
        return self.query_one(
            "SELECT * FROM timing_instruction WHERE source=? AND instruction_id=?",
            (source, instruction_id),
        )

    def fetch_by_status(self, statuses: tuple[str, ...]) -> list[dict]:
        marks = ",".join("?" for _ in statuses)
        return self.query(
            f"SELECT * FROM timing_instruction WHERE status IN ({marks}) ORDER BY rowid",
            tuple(statuses),
        )

    def count_active_by_source(self, source: str) -> int:
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM timing_instruction "
            "WHERE source=? AND status IN ('ACTIVE','WARMING_UP','PAUSED')",
            (source,),
        )
        return int(row["n"]) if row else 0

    def count_active_total(self) -> int:
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM timing_instruction "
            "WHERE status IN ('ACTIVE','WARMING_UP','PAUSED')"
        )
        return int(row["n"]) if row else 0

    def update_instruction_engine(
        self,
        source: str,
        instruction_id: str,
        status: str,
        feedback: str | None,
        remaining_bars: int | None = None,
        effective_from: str | None = None,
        anchor_bar: str | None = None,
        expires_bar: str | None = None,
    ) -> None:
        self.execute(
            "UPDATE timing_instruction SET status=?, feedback=?, remaining_bars=?, "
            "effective_from=COALESCE(?, effective_from), "
            "anchor_bar=COALESCE(?, anchor_bar), "
            "expires_bar=COALESCE(?, expires_bar) "
            "WHERE source=? AND instruction_id=?",
            (
                status,
                feedback,
                remaining_bars,
                effective_from,
                anchor_bar,
                expires_bar,
                source,
                instruction_id,
            ),
        )

    def set_remaining_bars(self, source: str, instruction_id: str, remaining: int) -> None:
        self.execute(
            "UPDATE timing_instruction SET remaining_bars=? "
            "WHERE source=? AND instruction_id=?",
            (remaining, source, instruction_id),
        )

    # ---------------- events ----------------

    def insert_instruction_event(
        self,
        source: str,
        instruction_id: str,
        producer_revision: int | None,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor: str,
        ts: str,
        snapshot: dict | None = None,
    ) -> None:
        self.execute(
            "INSERT INTO timing_instruction_event "
            "(source, instruction_id, producer_revision, event_type, from_status, "
            " to_status, actor, payload_snapshot, ts) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                source,
                instruction_id,
                producer_revision,
                event_type,
                from_status,
                to_status,
                actor,
                json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
                ts,
            ),
        )

    def fetch_instruction_events(self, source: str, instruction_id: str) -> list[dict]:
        return self.query(
            "SELECT * FROM timing_instruction_event "
            "WHERE source=? AND instruction_id=? ORDER BY id",
            (source, instruction_id),
        )

    # ---------------- alerts ----------------

    def insert_alert_event(
        self,
        alert_id: str,
        event_type: str,
        from_lifecycle: str | None,
        to_lifecycle: str | None,
        instruction_keys: str,
        payload: dict,
        ts: str,
    ) -> None:
        self.execute(
            "INSERT INTO timing_alert_event "
            "(alert_id, event_type, from_lifecycle, to_lifecycle, instruction_keys, "
            " payload_snapshot, ts) VALUES (?,?,?,?,?,?,?)",
            (
                alert_id,
                event_type,
                from_lifecycle,
                to_lifecycle,
                instruction_keys,
                json.dumps(payload, ensure_ascii=False),
                ts,
            ),
        )

    def fetch_alert_events_for_instruction(self, source: str, instruction_id: str) -> list[dict]:
        key = f"{source}|{instruction_id}"
        return self.query(
            "SELECT * FROM timing_alert_event WHERE instruction_keys LIKE ? ORDER BY id",
            (f"%{key}%",),
        )

    # ---------------- outbox ----------------

    def insert_outbox(self, alert_id: str, event_type: str, payload: dict, ts: str) -> None:
        self.execute(
            "INSERT INTO alert_outbox (alert_id, event_type, payload_json, created_at) "
            "VALUES (?,?,?,?)",
            (alert_id, event_type, json.dumps(payload, ensure_ascii=False), ts),
        )

    def fetch_due_outbox(self, now: datetime, limit: int = 200) -> list[dict]:
        now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return self.query(
            "SELECT * FROM alert_outbox WHERE delivery_status='pending' "
            "AND (next_retry_at IS NULL OR next_retry_at<=?) ORDER BY id LIMIT ?",
            (now_str, limit),
        )

    def mark_outbox_delivered(self, row_id: int, ts: str) -> None:
        self.execute(
            "UPDATE alert_outbox SET delivery_status='delivered', delivered_at=? WHERE id=?",
            (ts, row_id),
        )

    def mark_outbox_retry(
        self, row_id: int, attempts: int, next_retry: str, error: str, failed: bool = False
    ) -> None:
        status = "failed" if failed else "pending"
        self.execute(
            "UPDATE alert_outbox SET attempts=?, next_retry_at=?, last_error=?, "
            "delivery_status=? WHERE id=?",
            (attempts, next_retry, error, status, row_id),
        )
