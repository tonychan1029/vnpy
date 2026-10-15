# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS013 mom6 as_of 复算（阶段0-1；ROADMAP §1A 0-1）。

标签口径：as_of（生产判定侧 context_tags，point-in-time；GT 不参与建模）。
对照：GT 前瞻口径历史数字 +0.364（全样本）/+0.180（保留段）——已废，仅作
衰减参照，不得引用为证据。

口径升级（vs cand007_engine_tag.md 的 v0 复算）：
  ①后复权（splice_adjust 链式+坏点护栏，rs020 同款）——消除换月跳变对
    mom6 与 fwd 的污染；
  ②非重叠分块（步长=前瞻=20 根）；
  ③显著性：pooled Pearson 的 t 统计量 + 分块数；
  ④复权 vs 未复权双跑对照（量化换月污染幅度）。
判定基准（预注册）：breakout 条件 IC 显著为正（t≥2 且方向 6 品种 ≥4 正）
  → mom6 突破段条件化证据"存活"；否则 CAND-007 证据链正式关闭。

输出：assets/RS013/mom6_asof_recheck.md
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS013"

SYMBOLS = {"RB": "SHFE", "CU": "SHFE", "AG": "SHFE",
           "M": "DCE", "MA": "CZCE", "TA": "CZCE"}
HZ = 20          # 前瞻根数
I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(7)


def load_bars(sym: str, exch: str):
    rows = []
    with (DATA / exch / sym / f"{sym}.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append([r["datetime"], float(r["open"]), float(r["high"]),
                             float(r["low"]), float(r["close"]),
                             float(r.get("volume") or 0),
                             float(r.get("position") or 0)])
            except (ValueError, TypeError):
                continue
    return rows


def splice_adjust(rows: list[list]) -> int:
    """链式后复权（rs020 同款三信号评分≥2 + 坏点护栏）。返回跳过的坏点数。"""
    n = len(rows)
    if n < 2:
        return 0
    trs = [rows[0][I_H] - rows[0][I_L]]
    for i in range(1, n):
        trs.append(max(rows[i][I_H] - rows[i][I_L],
                       abs(rows[i][I_H] - rows[i - 1][I_C]),
                       abs(rows[i][I_L] - rows[i - 1][I_C])))
    atr = []
    for i in range(n):
        w = trs[max(0, i - 13): i + 1]
        atr.append(sum(w) / len(w))
    bad = 0
    for i in range(1, n):
        score = 0
        pc, op = rows[i - 1][I_C], rows[i][I_O]
        if pc > 0 and abs(op - pc) / pc > 0.008:
            score += 1
        if rows[i][I_OI] > 0 and rows[i - 1][I_OI] > 0 and \
                rows[i][I_OI] < rows[i - 1][I_OI] * 0.85:
            score += 1
        rng = rows[i][I_H] - rows[i][I_L]
        if atr[i] > 0 and rng > atr[i] * 2.5:
            score += 1
        if score >= 2:
            pc2, op2 = rows[i - 1][I_C], rows[i][I_O]
            if pc2 > 0 and op2 > 0:
                local = pc2 / op2
                if local <= 0.5 or local >= 2.0:
                    bad += 1
                    continue
                for j in range(i, n):
                    for k in (I_O, I_H, I_L, I_C):
                        rows[j][k] *= local
    return bad


def pearson(xs, ys):
    n = len(xs)
    if n < 30:
        return None, n, None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs) ** 0.5
    vy = sum((b - my) ** 2 for b in ys) ** 0.5
    if not vx or not vy:
        return None, n, None
    r = cov / (vx * vy)
    denom = 1 - r * r
    t = r * math.sqrt((n - 2) / denom) if denom > 0 else None
    return r, n, t


def pct_ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    for rank, i in enumerate(order):
        out[i] = rank / max(len(vals) - 1, 1)
    return out


def run_variant(adj: bool):
    buckets = {"breakout": ([], []), "all": ([], [])}
    per_sym = {}
    for sym, exch in SYMBOLS.items():
        rows = load_bars(sym, exch)
        rows.sort(key=lambda r: r[I_DT])
        if adj:
            splice_adjust(rows)
        tags = {}
        with (TAGS / f"{sym}_context_tags.csv").open(
                newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t = (r.get("context_tag") or "").strip().lower()
                if t:
                    tags[r["datetime"]] = t
        valid = []
        n = len(rows)
        for i in range(40, n - HZ, HZ):          # 非重叠分块
            if rows[i - 1][I_C] <= 0:
                continue
            fwd = rows[i + HZ][I_C] / rows[i][I_C] - 1
            valid.append((rows[i][I_C] / rows[i - 1][I_C] - 1, fwd,
                          tags.get(rows[i][I_DT], "")))
        if len(valid) < 50:
            continue
        ranks = pct_ranks([m for m, _, _ in valid])
        sym_ic = {}
        for name, cond in (("breakout", lambda t: t == "breakout"),
                           ("all", lambda t: True)):
            xs = [rk for (_, _, t), rk in zip(valid, ranks) if cond(t)]
            ys = [fw for (_, fw, t) in valid if cond(t)]
            ic, k, t = pearson(xs, ys)
            if ic is not None:
                buckets[name][0].extend(xs)
                buckets[name][1].extend(ys)
                sym_ic[name] = (ic, k, t)
        per_sym[sym] = sym_ic
    pooled = {}
    for name in ("breakout", "all"):
        ic, k, t = pearson(*buckets[name])
        pooled[name] = (ic, k, t)
    return pooled, per_sym


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    L = ["# RS013 mom6 as_of 复算（阶段0-1；v 判定侧标签+后复权+非重叠分块）", "",
         "- **标签口径：as_of**（生产判定侧 context_tags，point-in-time；GT 不参与）；",
         "- 对照（已废，仅衰减参照）：GT 前瞻口径 +0.364（全样本）/+0.180（保留段）；",
         "- 判定基准（预注册）：breakout 条件 IC t≥2 且 6 品种 ≥4 正 → 证据存活；",
         "  否则 CAND-007 证据链正式关闭。", ""]

    for adj, tag_name in ((True, "后复权"), (False, "未复权（对照）")):
        pooled, per_sym = run_variant(adj)
        L.append(f"## {tag_name}")
        for name in ("breakout", "all"):
            ic, k, t = pooled[name]
            if ic is None:
                L.append(f"- {name}: n 不足")
                continue
            sig = "✅" if (t is not None and t >= 2.0) else "❌"
            L.append(f"- **{name}**: IC {ic:+.4f}（分块 n={k}，t={t:.2f} {sig}）")
        L.append("")
        L.append("| 品种 | breakout IC(n, t) | all IC(n, t) |")
        L.append("|---|---|---|")
        pos = 0
        for sym, d in per_sym.items():
            e = d.get("breakout")
            a = d.get("all")
            if e and e[0] > 0:
                pos += 1
            L.append(f"| {sym} | "
                     + (f"{e[0]:+.4f}({e[1]}, t={e[2]:.2f})" if e else "-") + " | "
                     + (f"{a[0]:+.4f}({a[1]}, t={a[2]:.2f})" if a else "-") + " |")
        L.append(f"- breakout 方向为正的品种数：{pos}/6")
        L.append("")

    adj_pool, _ = run_variant(True)
    ic, k, t = adj_pool["breakout"]
    surv = ic is not None and t is not None and t >= 2.0
    L += ["## 预注册判读", "",
          f"- breakout 条件（后复权）：IC {ic:+.4f}（n={k}，t={t:.2f}）→ "
          + ("**证据存活 ✅**" if surv else "**证据链关闭 ❌**——CAND-007/mom6 "
            "突破段条件化不再作为立项依据，相关主线引用以本报告为准。"),
          "- 复权对照的意义：未复权列若显著高于后复权列，说明换月跳变本身"
          "贡献了虚假条件化收益（ 幻影动量）。"]
    out = OUT / "mom6_asof_recheck.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    print(f"adj breakout IC={ic:+.4f} n={k} t={t:.2f} survive={surv}")


if __name__ == "__main__":
    main()
