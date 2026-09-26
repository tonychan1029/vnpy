"""审批运维入口（最小 CLI）：pending / approve / reject。"""

from __future__ import annotations

import argparse
import os

from .engine import PatimingEngine


def _pending(eng, args) -> None:
    rows = eng.db.query(
        "SELECT source, instruction_id, reason_note, feedback "
        "FROM timing_instruction WHERE status='PENDING_APPROVAL' ORDER BY rowid")
    if not rows:
        print("（无待审批指令）")
    for r in rows:
        print(f"{r['source']}  {r['instruction_id']}  {r['reason_note'][:60]}")


def _approve(eng, args) -> None:
    with eng.lock:
        print(eng.approve_instruction(args.source, args.instruction_id))


def _reject(eng, args) -> None:
    with eng.lock:
        print(eng.reject_instruction(args.source, args.instruction_id))


def main() -> None:
    parser = argparse.ArgumentParser("vnpy_patiming.cli",
                                     description="择时指令审批运维入口")
    parser.add_argument("--db", default=os.environ.get("PATIMING_DB", "patiming.db"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending", help="列出待审批指令")
    p_ok = sub.add_parser("approve", help="批准（PENDING -> ACTIVE）")
    p_no = sub.add_parser("reject", help="拒绝（PENDING -> REVOKED）")
    for p in (p_ok, p_no):
        p.add_argument("source")
        p.add_argument("instruction_id")
    args = parser.parse_args()
    eng = PatimingEngine(args.db)
    try:
        {"pending": _pending, "approve": _approve, "reject": _reject}[args.cmd](eng, args)
    finally:
        eng.close()


if __name__ == "__main__":
    main()
