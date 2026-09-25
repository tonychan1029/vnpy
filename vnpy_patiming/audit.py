"""LLM 翻译对账（spec 10.2）：原始需求 -> 指令 -> 报警 链条报告。"""

from __future__ import annotations


def build_audit_report(db, source_prefix: str = "llm:") -> list[dict]:
    rows = db.query(
        "SELECT * FROM timing_instruction WHERE source LIKE ? ORDER BY rowid",
        (source_prefix + "%",),
    )
    report: list[dict] = []
    for row in rows:
        events = db.fetch_instruction_events(row["source"], row["instruction_id"])
        alerts = db.fetch_alert_events_for_instruction(row["source"], row["instruction_id"])
        report.append({
            "source": row["source"],
            "instruction_id": row["instruction_id"],
            "original_requirement": row["reason_note"],
            "status": row["status"],
            "context_tag": row["context_tag"],
            "valid_bars": row["valid_bars"],
            "timeline": [e["event_type"] for e in events],
            "alert_count": len(alerts),
            "alerts": [
                {"alert_id": a["alert_id"], "event_type": a["event_type"]}
                for a in alerts
            ],
        })
    return report


def render_markdown(report: list[dict]) -> str:
    lines = ["# LLM 翻译对账报告", ""]
    for item in report:
        lines.append(
            f"- [{item['instruction_id']}] {item['original_requirement']}"
            f" -> status={item['status']} alerts={item['alert_count']}"
            f" timeline={'/'.join(item['timeline'])}"
        )
    if not report:
        lines.append("（无 LLM 指令）")
    return "\n".join(lines)
