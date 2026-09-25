"""MCP write-face service (spec 8). Runs in-process with the engine so the
engine stays the single DB writer; a token-per-caller gate protects writes.

Requires the optional dependency: pip install fastmcp
"""

from __future__ import annotations

import os
import argparse

from .engine import PatimingEngine


def build_service(engine: PatimingEngine):
    try:
        from fastmcp import FastMCP  # fastmcp v4（含 mcp 2.x 兼容）
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("pip install fastmcp to run the MCP service") from exc

    token = os.environ.get("PATIMING_MCP_TOKEN", "")
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
    db_path = os.environ.get("PATIMING_DB", "patiming.db")
    engine = PatimingEngine(db_path)
    engine.start()
    service = build_service(engine)
    print(f"patiming auth configured: {bool(os.environ.get('PATIMING_MCP_TOKEN'))}", flush=True)
    parser = argparse.ArgumentParser(description="Patiming Engine MCP service")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8801)
    args = parser.parse_args()
    if args.transport != "stdio":
        service.settings.host = args.host
        service.settings.port = args.port
        # Allow LAN/Tailscale Host headers in the local test network. Writes
        # remain gated by PATIMING_MCP_TOKEN inside every tool.
        service.settings.transport_security.enable_dns_rebinding_protection = False
    service.run(transport=args.transport)


if __name__ == "__main__":
    main()
