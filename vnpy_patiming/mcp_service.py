"""MCP write-face service (spec 8). Runs in-process with the engine so the
engine stays the single DB writer; a token-per-caller gate protects writes.

Requires the optional dependency: pip install fastmcp
"""

from __future__ import annotations

import os
import argparse
import threading
from collections.abc import Callable
from pathlib import Path

from .engine import PatimingEngine
from .config import TIMEFRAME_MINUTES


def _configured_token() -> str:
    token = os.environ.get("PATIMING_MCP_TOKEN", "")
    token_file = os.environ.get("PATIMING_MCP_TOKEN_FILE", "")
    if not token and token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    return token


def _configured_strategy_token() -> str:
    token = os.environ.get("PATIMING_STRATEGY_MCP_TOKEN", "")
    token_file = os.environ.get("PATIMING_STRATEGY_MCP_TOKEN_FILE", "")
    if not token and token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    return token


def _warmup_live_task(
    engine: PatimingEngine,
    vt_symbol: str,
    exec_tf: str,
    feed=None,
) -> int:
    """Warm one task from its most recent closed execution-timeframe bars."""
    if engine.data_mode != "akshare_poll":
        return 0

    if feed is None:
        from .adapters import AkshareOneMinuteFeed

        feed = AkshareOneMinuteFeed()

    try:
        symbol, exchange = vt_symbol.rsplit(".", 1)
        bars = feed.fetch_minutes(
            symbol, exchange, str(TIMEFRAME_MINUTES[exec_tf])
        )
        current_minute = engine.clock().replace(second=0, microsecond=0)
        bars = [bar for bar in bars if bar.datetime < current_minute]
        count = engine.cfg["warmup_min_exec"]
        # The newest row may correspond to the QuotePoller's in-progress
        # snapshot minute; leave that transition to the live feed.
        warm_bars = bars[-(count + 1):-1]
        with engine.lock:
            task = engine.tasks.get((vt_symbol, exec_tf))
            if task is None or task.ready or task.ever_received:
                return 0
            for bar in warm_bars:
                task.on_exec_bar(bar)
        print(
            f"patiming warmup: {vt_symbol}/{exec_tf} "
            f"bars={len(warm_bars)} ready={task.ready}",
            flush=True,
        )
        return len(warm_bars)
    except Exception as exc:  # noqa: BLE001 - one symbol must not stop others
        print(f"patiming warmup failed: {vt_symbol}/{exec_tf}: {exc}", flush=True)
        return 0


def _start_live_task_warmup(engine: PatimingEngine) -> Callable[[str, str], None]:
    def warmup(symbol: str, exec_tf: str) -> None:
        threading.Thread(
            target=_warmup_live_task,
            args=(engine, symbol, exec_tf),
            name=f"patiming-warmup-{symbol}-{exec_tf}",
            daemon=True,
        ).start()

    return warmup


def _warmup_live_tasks(engine, feed=None) -> dict[tuple[str, str], int]:
    """Warm tasks that already existed when the service started."""
    engine.reconcile()
    if engine.data_mode != "akshare_poll" or not engine.tasks:
        return {}

    if feed is None:
        from .adapters import AkshareOneMinuteFeed

        feed = AkshareOneMinuteFeed()

    result: dict[str, int] = {}
    for (vt_symbol, exec_tf), task in sorted(engine.tasks.items()):
        result[(vt_symbol, exec_tf)] = _warmup_live_task(
            engine, vt_symbol, exec_tf, feed
        )
    return result


def build_service(engine: PatimingEngine):
    try:
        from fastmcp import FastMCP  # fastmcp v4（含 mcp 2.x 兼容）
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("pip install fastmcp to run the MCP service") from exc

    token = _configured_token()
    strategy_token = _configured_strategy_token()
    mcp = FastMCP("PatimingEngine")

    def _check(token_arg: str) -> str | None:
        if not token or token_arg != token:
            return "unauthorized"
        return None

    def _check_strategy(token_arg: str) -> str | None:
        if not strategy_token or token_arg != strategy_token:
            return "unauthorized"
        return None

    def _caller_source(token_arg: str, session_id: str) -> str | None:
        if token_arg == strategy_token and session_id == "hourly-selection":
            return "strategy:hourly-selection"
        if token_arg == token:
            return f"llm:{session_id}"
        return None

    @mcp.tool()
    def timing_instruction_upsert(
        token: str,
        session_id: str,
        payload: dict,
    ) -> dict:
        """Write/update a timing instruction. Source is injected server-side;
        any 'source' key in the payload is stripped and ignored."""
        denied = _check(token)
        if denied:
            return {"ok": False, "error": denied}
        if len(session_id) > 64 or not session_id:
            return {"ok": False, "error": "bad_session_id"}
        source = _caller_source(token, session_id)
        if source is None:
            return {"ok": False, "error": "bad_session_id"}
        return engine.submit_instruction(source, payload)

    @mcp.tool()
    def timing_instruction_revoke(
        token: str,
        session_id: str,
        instruction_id: str,
        producer_revision: int,
    ) -> dict:
        """Revoke an instruction owned by this session (source-scoped)."""
        denied = _check(token)
        if denied:
            return {"ok": False, "error": denied}
        source = _caller_source(token, session_id)
        if source is None:
            return {"ok": False, "error": "bad_session_id"}
        return engine.revoke(source, instruction_id, producer_revision)

    @mcp.tool()
    def timing_instruction_query(token: str, session_id: str,
                                 instruction_id: str | None = None) -> dict:
        """Query own instructions + feedback + alert history (source-scoped)."""
        denied = _check(token)
        if denied:
            return {"ok": False, "error": denied}
        source = _caller_source(token, session_id)
        if source is None:
            return {"ok": False, "error": "bad_session_id"}
        return engine.query(source, instruction_id)

    @mcp.tool()
    def strategy_selection_upsert(
        token: str,
        payload: dict,
    ) -> dict:
        """Write/update an approved strategy-agent selection instruction."""
        denied = _check_strategy(token)
        if denied:
            return {"ok": False, "error": denied}
        source = "strategy:hourly-selection"
        return engine.submit_instruction(source, payload)

    @mcp.tool()
    def strategy_selection_revoke(
        token: str,
        instruction_id: str,
        producer_revision: int,
    ) -> dict:
        """Revoke an instruction owned by the strategy selection agent."""
        denied = _check_strategy(token)
        if denied:
            return {"ok": False, "error": denied}
        return engine.revoke(
            "strategy:hourly-selection", instruction_id, producer_revision
        )

    @mcp.tool()
    def strategy_selection_query(
        token: str,
        instruction_id: str | None = None,
    ) -> dict:
        """Query instructions and alerts owned by the selection agent."""
        denied = _check_strategy(token)
        if denied:
            return {"ok": False, "error": denied}
        return engine.query(
            "strategy:hourly-selection", instruction_id
        )

    @mcp.tool()
    def timing_health(token: str, session_id: str) -> dict:
        """Read-only engine runtime health for authorized callers."""
        source = _caller_source(token, session_id)
        if source is None:
            return {"ok": False, "error": "unauthorized"}
        return engine.health_snapshot()

    return mcp


def main() -> None:  # pragma: no cover - manual entry point
    parser = argparse.ArgumentParser(description="Patiming Engine MCP service")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8801)
    args = parser.parse_args()

    enable_poller = os.environ.get(
        "PATIMING_ENABLE_POLLER", "0"
    ).lower() in {"1", "true", "yes"}
    data_mode = os.environ.get(
        "PATIMING_DATA_MODE", "akshare_poll" if enable_poller else "ctp_tick"
    )
    db_path = os.environ.get("PATIMING_DB", "patiming.db")
    require_approval = os.environ.get("PATIMING_REQUIRE_APPROVAL", "1").lower() in {
        "1",
        "true",
        "yes",
    }
    engine = PatimingEngine(
        db_path,
        {"require_approval": require_approval},
        data_mode=data_mode,
    )
    poller = None

    try:
        redis_url = os.environ.get("PATIMING_REDIS_URL", "")
        if redis_url:
            from .delivery import make_redis_stream_handler

            handler = make_redis_stream_handler(
                redis_url, os.environ.get("PATIMING_STREAM", "patiming:alerts")
            )
            handler.ping()
            engine.register_delivery_handler(handler)

        if enable_poller:
            from .quote_poller import QuotePoller

            poller = QuotePoller(
                engine,
                interval_s=float(os.environ.get("PATIMING_POLL_INTERVAL_S", "5")),
            )

        engine.task_warmup_hook = _start_live_task_warmup(engine)
        engine.start()
        _warmup_live_tasks(engine)
        if poller is not None:
            poller.start()
        service = build_service(engine)
        print(f"patiming auth configured: {bool(_configured_token())}", flush=True)
        run_kwargs = {}
        if args.transport != "stdio":
            # FastMCP 4 configures HTTP transports through run kwargs.
            run_kwargs = {
                "host": args.host,
                "port": args.port,
                "host_origin_protection": False,
            }
        service.run(transport=args.transport, **run_kwargs)
    finally:
        if poller is not None:
            poller.stop()
        engine.close()


if __name__ == "__main__":
    main()
