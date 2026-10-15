# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS019 环节1：趋势/背景判定质量历史审计（Lead 补做，原 teammate 中断）。

复刻口径：PABackgroundEngine（pa/background.py）逐日滚动 120 根窗判定
  BULL/BEAR/CHOP（滚动窗使摆动点 5 右确认自然实现）；
数据：load_daily（后复权日线，2015 起，工程 _detect_and_splice 同款，坏点护栏）。

度量（存原始收益、方向在聚合层施加——防口径串扰）：
  A. 方向胜率曲线：引擎趋势日（方向=引擎判定） vs 朴素规则（全交易日，
     方向=close>SMA20），后 1/5/10/20 根方向调整收益胜率，全样本/in/out；
  B. CHOP 过滤有效性：CHOP 日 vs 趋势日的 10 根 |净位移|/ATR14；
  C. 判定持续性：趋势段长度分布 + 状态转移结构。

输出：assets/RS019/trend_quality.md
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.rs017_trendpullback_replay import analyze, load_daily  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "assets" / "RS019"
SYMS = {"RB": "SHFE", "CU": "SHFE", "M": "DCE", "TA": "CZCE", "MA": "CZCE"}
LOOKBACK = 120
SPLIT = "2022-01-01"
HORIZONS = (1, 5, 10, 20)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    recs = []   # (sym, day, engine_cls, naive_dir, raw_rets{k}, disp10)
    for sym, exch in SYMS.items():
        days, bars = load_daily(sym, exch)
        highs = [b[0] for b in bars]
        lows = [b[1] for b in bars]
        closes = [b[2] for b in bars]
        n = len(bars)
        sma20 = [None] * n
        for i in range(19, n):
            sma20[i] = sum(closes[i - 19: i + 1]) / 20
        atr14 = [None] * n
        trs = []
        for i in range(1, n):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
            trs.append(tr)
            if len(trs) >= 14:
                atr14[i] = sum(trs[-14:]) / 14
        start = LOOKBACK + 25
        for d in range(start, n - max(HORIZONS)):
            w0 = d - LOOKBACK + 1
            trend, _e, _s, _r = analyze(highs[w0: d + 1], lows[w0: d + 1],
                                        closes[w0: d + 1])
            cls = trend if trend in ("long", "short") else "chop"
            if sma20[d] is None or atr14[d] in (None, 0):
                continue
            raw = {k: closes[d + k] / closes[d] - 1 for k in HORIZONS}
            naive_dir = 1 if closes[d] > sma20[d] else -1
            disp10 = abs(closes[d + 10] - closes[d]) / atr14[d]
            recs.append((sym, days[d], cls, naive_dir, raw, disp10))
    recs.sort(key=lambda r: (r[0], r[1]))

    def dir_stats(rows, target):
        """target: 'engine'（引擎趋势日）或 'naive'（全日朴素方向）。"""
        vals = {k: [] for k in HORIZONS}
        for sym, day, cls, nd, raw, _d in rows:
            if target == "engine" and cls not in ("long", "short"):
                continue
            d = 1 if cls == "long" else -1
            if target == "naive":
                d = nd
            for k in HORIZONS:
                vals[k].append(d * raw[k])
        out = {}
        for k in HORIZONS:
            v = vals[k]
            out[k] = (len(v), sum(1 for x in v if x > 0) / len(v),
                      sum(v) / len(v)) if v else None
        return out

    def fmt(h):
        return (f"{h[1]:.1%}（均值 {h[2]:+.2%}，n={h[0]}）" if h else "-")

    L = ["# RS019 环节1：趋势/背景判定质量审计（后复权日线，Lead 补做）", "",
         f"- 窗口=滚动 {LOOKBACK} 根、引擎同款判定（摆动点+EMA21+HH/HL）；",
         "- 引擎口径=仅趋势日（CHOP 不出方向）；朴素口径=全部交易日按",
         "  close>SMA20 取方向；收益=方向调整收盘口径、无成本；",
         "- 5/10 子集、日线合成近似。", ""]

    eng = dir_stats(recs, "engine")
    niv = dir_stats(recs, "naive")
    L += ["## A. 方向胜率曲线（引擎趋势日 vs 朴素 SMA20 全日）", "",
          "| 口径 | 规则 | " + " | ".join(f"+{k}日胜率（均值）" for k in HORIZONS) + " |",
          "|---|---|" + "---|" * len(HORIZONS)]
    for tag, cond in (("全样本", lambda d: True),
                      ("in <2022", lambda d: d < SPLIT),
                      ("out ≥2022", lambda d: d >= SPLIT)):
        sub = [r for r in recs if cond(r[1])]
        e = dir_stats(sub, "engine")
        nv = dir_stats(sub, "naive")
        L.append(f"| {tag} | 引擎 趋势日 | " +
                 " | ".join(fmt(e[k]) for k in HORIZONS) + " |")
        L.append(f"| {tag} | 朴素 SMA20 | " +
                 " | ".join(fmt(nv[k]) for k in HORIZONS) + " |")

    # A2. 引擎趋势日 +10 分品种
    L += ["", "## A2. 引擎趋势日 +10 日分品种", "",
          "| 品种 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    for sym in SYMS:
        sub = [r for r in recs if r[0] == sym]
        h = dir_stats(sub, "engine")
        h10 = h[10]
        if h10:
            L.append(f"| {sym} | {h10[0]} | {h10[1]:.1%} | {h10[2]:+.2%} |")

    # B. CHOP 过滤有效性
    chop_disp = [r[5] for r in recs if r[2] == "chop"]
    trend_disp = [r[5] for r in recs if r[2] in ("long", "short")]
    L += ["", "## B. CHOP 过滤有效性（10 根 |净位移|/ATR14，低=低效期）", ""]
    if trend_disp and chop_disp:
        L += [f"- 趋势日：均值 {sum(trend_disp) / len(trend_disp):.2f}×ATR（n={len(trend_disp)}）",
              f"- CHOP 日：均值 {sum(chop_disp) / len(chop_disp):.2f}×ATR（n={len(chop_disp)}）",
              f"- CHOP 日占比：{len(chop_disp) / len(recs):.1%}",
              "- 判读：CHOP 日位移若接近趋势日 → 背景过滤在'剔除低效期'上无增量"]

    # C. 判定持续性
    L += ["", "## C. 判定持续性", "",
          "| 品种 | 趋势段中位长(日) | 直接翻转占比 | 经CHOP占比 |", "|---|---|---|---|"]
    by_sym = {s: [r for r in recs if r[0] == s] for s in SYMS}
    for sym in SYMS:
        seq = [(r[1], r[2]) for r in by_sym[sym]]
        seg_lens, direct, via = [], 0, 0
        cur, ln = None, 0
        last_trend = None
        saw_chop = False
        for _d, cls in seq:
            if cls == "chop":
                saw_chop = True
                continue
            if cls != cur:
                if cur is not None:
                    seg_lens.append(ln)
                if last_trend is not None and cls != last_trend:
                    if saw_chop:
                        via += 1
                    else:
                        direct += 1
                cur, ln = cls, 1
            else:
                ln += 1
            last_trend = cls
            saw_chop = False
        seg_lens.sort()
        med = seg_lens[len(seg_lens) // 2] if seg_lens else 0
        tot = direct + via
        L.append(f"| {sym} | {med} | {direct / tot:.0%} | {via / tot:.0%} |"
                 if tot else f"| {sym} | 0 | - | - |")

    L += ["", "机械判读（事前声明）：引擎趋势日 +10 日胜率显著 >50% 且优于朴素",
          "SMA20 对照 → 方向量化成立；≈50% 或不如对照 → 方向量化需重构",
          "（引 RS001 三因子：趋势强度/回调衰竭/失败捕捉）。"]

    out = OUT / "trend_quality.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    e10 = dir_stats(recs, "engine")[10]
    n10 = dir_stats(recs, "naive")[10]
    print(f"+10日: 引擎 {e10[1]:.1%}/{e10[2]:+.2%} vs 朴素 {n10[1]:.1%}/{n10[2]:+.2%}")


if __name__ == "__main__":
    main()
