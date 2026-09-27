"""MCP write-face service (spec 8). Runs in-process with the engine so the
engine stays the single DB writer; a token-per-caller gate protects writes.

Requires the optional dependency: pip install fastmcp
"""

from __future__ import annotations

import os
import argparse
from pathlib import Path

from .engine import PatimingEngine


def _configured_token() -> str:
    token = os.environ.get("PATIMING_MCP_TOKEN", "")
    token_file = os.environ.get("PATIMING_MCP_TOKEN_FILE", "")
    if not token and token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    return token


def build_service(engine: PatimingEngine):
    try:
        from fastmcp import FastMCP  # fastmcp v4（含 mcp 2.x 兼容）
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("pip install fastmcp to run the MCP service") from exc

    token = _configured_token()
    mcp = FastMCP("PatimingEngine")

    def _check(token_arg: str) -> str | None:
        if not token or token_arg != token:
            return "unauthorized"
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
        return engine.submit_instruction(f"llm:{session_id}", payload)

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
        return engine.revoke(f"llm:{session_id}", instruction_id, producer_revision)

    @mcp.tool()
    def timing_instruction_query(token: str, session_id: str,
                                 instruction_id: str | None = None) -> dict:
        """Query own instructions + feedback + alert history (source-scoped)."""
        denied = _check(token)
        if denied:
            return {"ok": False, "error": denied}
        return engine.query(f"llm:{session_id}", instruction_id)

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

        engine.start()
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
