# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS012 真值侧批量标注器：对 6 主连 60m 数据计算操作性真值标签。

只读外部数据（TRADEPLAY_DATA），产物写 strategy_research/assets/RS012/。
用途：验证 GT 定义可计算、给出标签分布、为混淆矩阵备好真值侧。
判定标签侧（引擎 context_tag）由工程导出后另行对齐。
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from methods.context_eval import ground_truth_label  # noqa: E402

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = ROOT.parent / "assets" / "RS012"

SYMBOLS = {
    "RB": DATA / "SHFE" / "RB" / "RB.csv",
    "CU": DATA / "SHFE" / "CU" / "CU.csv",
    "AG": DATA / "SHFE" / "AG" / "AG.csv",
    "M": DATA / "DCE" / "M" / "M.csv",
    "MA": DATA / "CZCE" / "MA" / "MA.csv",
    "TA": DATA / "CZCE" / "TA" / "TA.csv",
}

STEP = 4          # 每 4 根取一个 as_of（20根窗口=步长4 即窗口间重叠75%，够密）
ATR_N = 14


def load(path: Path):
    dts, highs, lows, closes = [], [], [], []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dts.append(row["datetime"])
            highs.append(float(row["high"]))
            lows.append(float(row["low"]))
            closes.append(float(row["close"]))
    return dts, highs, lows, closes


def atr_series(highs, lows, closes, n=ATR_N):
    out = [None] * len(closes)
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
        if len(trs) >= n:
            out[i] = sum(trs[-n:]) / n
    return out


def episode_stats(labels: list[str]):
    """连续同标签段（episode）长度统计 + 每 100 根切换次数。"""
    runs: dict[str, list[int]] = {}
    switches = 0
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            lab = labels[start]
            runs.setdefault(lab, []).append(i - start)
            if i < len(labels):
                switches += 1
            start = i
    n = max(len(labels), 1)
    stats = {lab: (sum(v) / len(v), sorted(v)[len(v) // 2], len(v))
             for lab, v in runs.items()}
    return stats, switches * 100.0 / n


def run(horizon: int, suffix: str):
    out = OUT
    agg = {}
    for sym, path in SYMBOLS.items():
        if not path.exists():
            print(f"[skip] {sym}: {path} 不存在")
            continue
        dts, highs, lows, closes = load(path)
        atrs = atr_series(highs, lows, closes)
        rows = []
        counter: Counter = Counter()
        for as_of in range(40, len(closes) - horizon - 1, STEP):
            atr = atrs[as_of]
            if atr is None or atr <= 0:
                continue
            gt = ground_truth_label(closes, atr, as_of, horizon=horizon)
            if gt.label == "UNDEFINED":
                continue
            counter[gt.label] += 1
            rows.append((dts[as_of], gt.label))
        total = sum(counter.values())
        agg[sym] = (total, counter)
        with (out / f"{sym}_gt_labels{suffix}.csv").open("w", newline="",
                                                         encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["datetime", "gt_label"])
            w.writerows(rows)
        print(f"[ok] h={horizon} {sym}: bars={len(closes)} samples={total}")
    return agg


def write_summary(agg: dict, horizon: int, suffix: str):

    lines = ["# RS012 真值侧标注汇总（STEP=%d, horizon=20, ATR%d）" % (STEP, ATR_N),
             "",
             "| 品种 | 有效样本 | " + " | ".join(
                 sorted({k for _, c in agg.values() for k in c})) + " |",
             "|------" * 2 + "|" + "------|" * 6]
    labels_set = sorted({k for _, c in agg.values() for k in c})
    for sym, (total, counter) in agg.items():
        pcts = [f"{counter[l] / total * 100:.1f}%" if total else "-" for l in labels_set]
        lines.append(f"| {sym} | {total} | " + " | ".join(pcts) + " |")

    lines += ["", f"## 样本内外分布（in: <2022-01-01，out: >=2022-01-01；占比）", ""]
    lines += [f"| 品种 | 期 | " + " | ".join(labels_set) + " |",
              "|" + "-" * 6 + "|" + "-" * 6 + "|" + "-" * 6 + "|" * len(labels_set)]
    SPLIT = "2022-01-01"
    for sym in SYMBOLS:
        csv_path = OUT / f"{sym}_gt_labels{suffix}.csv"
        if not csv_path.exists():
            continue
        with csv_path.open(newline="", encoding="utf-8") as f:
            rows = [(r["datetime"], r["gt_label"]) for r in csv.DictReader(f)]
        for tag, cond in (("in", lambda d: d < SPLIT),
                          ("out", lambda d: d >= SPLIT)):
            sub = [l for d, l in rows if cond(d)]
            if not sub:
                continue
            c = Counter(sub)
            n = len(sub)
            cells = [f"{c[l] / n * 100:.1f}%" for l in labels_set]
            lines.append(f"| {sym} | {tag}({n}) | " + " | ".join(cells) + " |")

    lines += ["", f"## Episode 统计（horizon={horizon}；均值/中位数为样本数，"
              f"样本间隔 {STEP} 根 K）", ""]
    epi_head = "| 品种 | 每100根切换 | " + " | ".join(labels_set) + " |"
    lines += [epi_head, "|-" * 2 + "|" + "-" * 6 + "|" * len(labels_set)]
    for sym, path in SYMBOLS.items():
        csv_path = OUT / f"{sym}_gt_labels{suffix}.csv"
        if not csv_path.exists():
            continue
        with csv_path.open(newline="", encoding="utf-8") as f:
            labs = [r["gt_label"] for r in csv.DictReader(f)]
        stats, sw = episode_stats(labs)
        cells = []
        for lab in labels_set:
            if lab in stats:
                m, med, cnt = stats[lab]
                cells.append(f"{m:.1f}/{med:.0f}/{cnt}")
            else:
                cells.append("-")
        lines.append(f"| {sym} | {sw:.1f} | " + " | ".join(cells) + " |")
    lines[0] = f"# RS012 真值侧标注汇总（STEP={STEP}, horizon={horizon}, ATR{ATR_N}）"
    (OUT / f"summary{suffix}.md").write_text("\n".join(lines) + "\n",
                                             encoding="utf-8")
    print("summary ->", OUT / f"summary{suffix}.md")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for h, sfx in ((20, ""), (40, "_h40")):
        agg = run(h, sfx)
        write_summary(agg, h, sfx)
