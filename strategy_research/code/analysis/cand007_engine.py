# RESEARCH ONLY - 未获用户批准不得正式运行
"""CAND-007 引擎标签版复算：mom6 在「引擎 breakout 标签」下的条件 IC。

GT 版（RS013 §2a）用前瞻真值，不可交易；本版用生产判定侧 v0 引擎标签
（point-in-time，可交易）。预期因标签噪声（精确率 49%）而衰减但方向为正。
对照：全样本无条件 IC。口径与 RS013 相同（步长 20、品种内百分位秩、pooled）。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS013"

SYMBOLS = {"RB": (DATA / "SHFE" / "RB" / "RB.csv",
                  TAGS / "RB_context_tags.csv"),
           "CU": (DATA / "SHFE" / "CU" / "CU.csv",
                  TAGS / "CU_context_tags.csv"),
           "AG": (DATA / "SHFE" / "AG" / "AG.csv",
                  TAGS / "AG_context_tags.csv"),
           "M": (DATA / "DCE" / "M" / "M.csv",
                 TAGS / "M_context_tags.csv"),
           "MA": (DATA / "CZCE" / "MA" / "MA.csv",
                  TAGS / "MA_context_tags.csv"),
           "TA": (DATA / "CZCE" / "TA" / "TA.csv",
                  TAGS / "TA_context_tags.csv")}
H = 20
HZ = 20


def pearson(xs, ys):
    n = len(xs)
    if n < 30:
        return None, n
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs) ** 0.5
    vy = sum((b - my) ** 2 for b in ys) ** 0.5
    return (cov / (vx * vy)) if vx and vy else None, n


def pct_ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    for rank, i in enumerate(order):
        out[i] = rank / max(len(vals) - 1, 1)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    buckets = {"engine_breakout": ([], []),
               "all": ([], [])}
    per_sym_detail = {}
    for sym, (dpath, tpath) in SYMBOLS.items():
        dts, o, h, l, c, v = [], [], [], [], [], []
        with dpath.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                o.append(float(r["open"]))
                h.append(float(r["high"]))
                l.append(float(r["low"]))
                c.append(float(r["close"]))
                v.append(float(r["volume"]))
        tags = {}
        with tpath.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t = (r.get("context_tag") or "").strip().lower()
                if t:
                    tags[r["datetime"]] = t
        valid = []
        for i in range(40, len(c) - HZ, H):
            if c[i - 6] <= 0:
                continue
            tag = tags.get(dts[i], "")
            fwd = c[i + HZ] / c[i] - 1
            valid.append((i, c[i] / c[i - 6] - 1, fwd, tag))
        if len(valid) < 50:
            continue
        ranks = pct_ranks([m for _, m, _, _ in valid])
        sym_ic = {}
        for name, cond in (("engine_breakout", lambda t: t == "breakout"),
                           ("all", lambda t: True)):
            xs = [rk for (_, _, _, t), rk in zip(valid, ranks) if cond(t)]
            ys = [fw for (_, _, fw, t) in valid if cond(t)]
            ic, n = pearson(xs, ys)
            if ic is not None:
                buckets[name][0].extend(xs)
                buckets[name][1].extend(ys)
                sym_ic[name] = (ic, n)
        per_sym_detail[sym] = sym_ic
    lines = ["# CAND-007 引擎标签版复算（mom6 × 引擎 breakout 标签，pooled rank IC）", "",
             f"- 前瞻 {HZ} 根，步长 {H}，标签=生产判定侧 v0（point-in-time）", ""]
    for name in ("engine_breakout", "all"):
        ic, n = pearson(*buckets[name])
        lines.append(f"- **{name}**: IC = "
                     + (f"{ic:+.3f} (n={n})" if ic is not None else "n 不足"))
    lines.append("")
    lines.append("| 品种 | engine_breakout IC(n) | 全样本 IC(n) |")
    lines.append("|---|---|---|")
    for sym, d in per_sym_detail.items():
        e = d.get("engine_breakout")
        a = d.get("all")
        lines.append(f"| {sym} | "
                     + (f"{e[0]:+.3f}({e[1]})" if e else "-") + " | "
                     + (f"{a[0]:+.3f}({a[1]})" if a else "-") + " |")
    lines += ["", "判读基准：GT 版 IC +0.364（全样本）/+0.180（保留段）。"
              "引擎版衰减幅度≈1−精确率(49%)的预期区间；方向为正即过滤器可交易化成立。"]
    (OUT / "cand007_engine_tag.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")
    print("->", OUT / "cand007_engine_tag.md")


if __name__ == "__main__":
    main()
