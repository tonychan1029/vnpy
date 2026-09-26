"""调参前后对比：基线=修复前首触逻辑的真实批量测量（非合成）。"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from vnpy_patiming._batch_probe import OVERRIDES, SYMBOLS, run_symbol  # noqa: E402
from vnpy_patiming.adapters import AkshareOneMinuteFeed  # noqa: E402


BEFORE = {  # 首触接刀逻辑（已由真实批量测量留档）
    "RB0.SHFE": {"total": 12, "structure": 10, "fake": 2, "breakout": 0},
    "CU0.SHFE": {"total": 19, "structure": 18, "fake": 0, "breakout": 1},
    "AG0.SHFE": {"total": 16, "structure": 14, "fake": 2, "breakout": 0},
    "MA0.CZCE": {"total": 17, "structure": 16, "fake": 0, "breakout": 1},
    "TA0.CZCE": {"total": 28, "structure": 25, "fake": 1, "breakout": 1},
}


def main() -> None:
    os.makedirs(os.path.join(os.path.dirname(__file__), "output"), exist_ok=True)
    feed = AkshareOneMinuteFeed()
    rows = []
    for symbol, exchange in SYMBOLS:
        vt = f"{symbol}.{exchange}"
        result = run_symbol(feed, symbol, exchange)
        alerts = result.get("alerts", {})
        structure = sum(v for k, v in alerts.items() if k.startswith("STRUCTURE"))
        total = sum(alerts.values())
        triggered = result.get("triggered", 0)
        rows.append({"vt": vt, "before": BEFORE.get(vt, {}).get("total", 0),
                     "after": total, "structure_after": structure,
                     "triggered": triggered,
                     "note": "canonical修复新增" if vt == "M0.DCE" else ""})
        print(vt, result)

    fig, ax = plt.subplots(figsize=(11, 5))
    xs = range(len(rows))
    ax.bar([x - 0.2 for x in xs], [r["before"] for r in rows], width=0.4,
           label="before（首触接刀）", color="#d62728")
    ax.bar([x + 0.2 for x in xs], [r["after"] for r in rows], width=0.4,
           label="after（v2 二次测试确认）", color="#2ca02c")
    for x, r in zip(xs, rows):
        ax.text(x + 0.2, r["after"] + 0.4, str(r["after"]), ha="center", fontsize=9)
        ax.text(x - 0.2, r["before"] + 0.4, str(r["before"]), ha="center", fontsize=9)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([r["vt"] for r in rows])
    ax.set_ylabel("真实回放预警数（1023 根 1m/品种）")
    ax.set_title("PullbackConfirm v2 前后对比：预警数量显著收敛")
    ax.legend()
    fig.tight_layout()
    out = os.path.join(os.path.dirname(__file__), "output", "tuning_before_after.png")
    fig.savefig(out, dpi=130)
    print("chart:", out)


if __name__ == "__main__":
    main()
