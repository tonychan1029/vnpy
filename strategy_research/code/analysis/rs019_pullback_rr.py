# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS019 环节2：回调到位判定与 RR 结构的历史审计（选品质量口径，非可交易回测）。

问题：
  ①回调买入（趋势背景 + EMA20 贴近）是否有超额收益？
  ②摆动点支撑/压力是否真实有效（回踩不破 vs 破位）？
  ③RR 过滤（≥1.5 闸门 / 分桶）是否筛出更高质量入场？
特别对照 MTG004：EMA20_PULLBACK（60m 触碰接刀，基线 −0.202、12/12 年负）
已否决——本审计检验日线 EMA20 回调（趋势背景内）是否同样无效。

方法：
  - 复用 rs017_trendpullback_replay.load_daily（60m→工程同款后复权→日线，
    2015 起，坏点护栏）与 analyze（引擎同款 trend/EMA20/support/resistance，
    pivot5,5+CCI 聚类+EMA21 斜率+HH/HL）；逐日滚动 120 根窗，start=LOOKBACK+15；
  - 贴近事件：|close−EMA20| ≤ max(0.5×ATR14, 0.005×close)
    （MarketPullback 15m MA20 贴近阈值的日线近似；ATR14=窗内 14 根 TR 简单均值）；
  - 2×2 因子对照分离"背景"与"回调"：趋势/CHOP × 贴近/未贴近，
    另列全部交易日 raw 漂移基线；CHOP 无引擎方向，收益用 raw
    （=多头口径；空头镜像=取负，机械对称）；
  - 收益：+5/+10/+20 交易日方向调整（自事件日收盘，long 原值 / short 取负），
    无成本无执行建模；窗口重叠（逐日事件）；
  - 支撑有效性：BULL 日 |close−support|≤1×ATR14（回踩支撑），后 10 日：
    破位=任一收盘<support×0.98；反弹=未破位且 +10 日收盘>事件日收盘；
    守住未顺向=其余；BEAR 镜像（收盘>pressure×1.02 破位，+10 日<事件日收盘
    为顺向）；另列远离支撑（>1×ATR）对照行；
  - RR：趋势+贴近事件按生产口径算 rr，RR≥1.5 闸门 pass/fail 对照 +
    分桶 <2 / 2-3 / ≥3，比较 +20 日收益与胜率。
诚实声明：生产池 10 主连中本地 60m 仅覆盖 RB/CU/M/TA/MA（5/10 子集）；
日线由 60m 合成（近似 akshare 日线）；后复权口径（DEC006）；收盘口径
非执行口径；机械判读阈值（±0.3% / 10pp）为事前声明。

输出：assets/RS019/pullback_rr.md（另打印关键数字到控制台）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.rs017_trendpullback_replay import (  # noqa: E402
    analyze, ema_series, find_pivot_swings, load_daily)

OUT = ROOT.parent / "assets" / "RS019"
SYMS = {"RB": "SHFE", "CU": "SHFE", "M": "DCE", "TA": "CZCE", "MA": "CZCE"}
LOOKBACK = 120
START = LOOKBACK + 15
HORIZONS = (5, 10, 20)
PROX_ATR, PROX_PCT = 0.5, 0.005     # 贴近阈值 max(0.5×ATR14, 0.5%×价)
RETEST_ATR = 1.0                    # 回踩支撑/压力：|close-位|≤1×ATR14
BRK_LO, BRK_HI = 0.98, 1.02         # 破位缓冲：support×0.98 / pressure×1.02
RR_GATE = 1.5
SPLIT = "2022-01-01"
BG_TH = 0.003                       # 机械判读阈值（事前声明）：±0.3%
PP_TH = 0.10                        # 机械判读阈值（事前声明）：10pp


def atr14(highs, lows, closes):
    """窗内 ATR14：TR 简单均值（首根 TR=h−l），与 rs017 复权 ATR 同风格。"""
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    w = trs[-14:]
    return sum(w) / len(w)


def grp(rec):
    """2×2 因子分组：趋势/CHOP × 贴近/未贴近。"""
    if rec["trend"] != "CHOP":
        return "T_NEAR" if rec["near"] else "T_FAR"
    return "C_NEAR" if rec["near"] else "C_FAR"


def ret(rec, k):
    """方向调整收益：long 原值 / short 取负；CHOP=raw（多头口径）。"""
    f = rec["fwd"].get(k)
    if f is None:
        return None
    return -f if rec["trend"] == "short" else f


def srat(sub, k):
    xs = [x for x in (ret(r, k) for r in sub) if x is not None]
    if not xs:
        return 0, None, None
    return (len(xs), sum(1 for x in xs if x > 0) / len(xs), sum(xs) / len(xs))


def mmean(sub, k):
    _n, _w, m = srat(sub, k)
    return m


def fmt_cell(sub, k):
    n, w, m = srat(sub, k)
    return f"{n} / {w:.1%} / {m:+.2%}" if n else "0 / - / -"


def md_table(title, rows, note=None):
    L = ["", f"## {title}", "",
         "| 口径 | +5日 n/胜率/均值 | +10日 n/胜率/均值 | +20日 n/胜率/均值 |",
         "|---|---|---|---|"]
    for name, sub in rows:
        L.append("| " + name + " | " + " | ".join(
            fmt_cell(sub, k) for k in HORIZONS) + " |")
    if note:
        L += ["", note]
    return L


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    recs = []
    for sym, exch in SYMS.items():
        days, bars = load_daily(sym, exch)
        highs = [b[0] for b in bars]
        lows = [b[1] for b in bars]
        closes = [b[2] for b in bars]
        n = len(bars)
        cnt = 0
        for d in range(START, n - 10):
            w0 = d - LOOKBACK + 1
            hw, lw, cw = highs[w0:d + 1], lows[w0:d + 1], closes[w0:d + 1]
            trend, entry, sup, res = analyze(hw, lw, cw)
            e20 = entry if trend else ema_series(cw, 20)[-1]
            if e20 is None:
                continue
            a = atr14(hw, lw, cw)
            c0 = closes[d]
            near = abs(c0 - e20) <= max(PROX_ATR * a, PROX_PCT * c0)
            rr = None
            brk = None
            if trend == "long":
                rr = (res - entry) / (entry - sup) if entry > sup else 0.0
                brk = any(closes[j] < sup * BRK_LO
                          for j in range(d + 1, d + 11))
                lvl_dist = abs(c0 - sup)
            elif trend == "short":
                rr = (entry - sup) / (res - entry) if res > entry else 0.0
                brk = any(closes[j] > res * BRK_HI
                          for j in range(d + 1, d + 11))
                lvl_dist = abs(c0 - res)
            else:
                lvl_dist = None
            recs.append({
                "sym": sym, "i": d, "date": days[d],
                "trend": trend or "CHOP", "e20": e20, "atr": a,
                "near": near, "sup": sup, "res": res, "rr": rr, "brk": brk,
                "lvl_dist": lvl_dist, "c0": c0, "lo": lw[-1], "hi": hw[-1],
                "fwd": {k: closes[d + k] / c0 - 1.0
                        for k in HORIZONS if d + k <= n - 1}})
            cnt += 1
        print(f"[{sym}] 日线 {n} 根，扫描 {cnt} 个交易日节点")

    # ── episode 首日（连续同向贴近事件只留首日，防持续趋势重复计数）──
    by_sym = {}
    for r in recs:
        by_sym.setdefault(r["sym"], []).append(r)
    for rs in by_sym.values():
        prev = None
        for r in rs:
            if grp(r) == "T_NEAR":
                r["ep"] = r["trend"] != prev
                prev = r["trend"]
            else:
                prev = None
                r["ep"] = False

    G = {g: [r for r in recs if grp(r) == g]
         for g in ("T_NEAR", "T_FAR", "C_NEAR", "C_FAR")}
    tn, tf, cn, cf = G["T_NEAR"], G["T_FAR"], G["C_NEAR"], G["C_FAR"]
    allr = recs
    ep = [r for r in recs if r.get("ep")]

    L = ["# RS019 环节2：回调到位判定与 RR 结构的历史审计（RESEARCH ONLY）", "",
         "- **RESEARCH ONLY — 选品质量口径，非可交易回测**；无成本/滑点/执行建模；",
         "- 子集声明：生产池 10 主连中本地 60m 仅覆盖 RB/CU/M/TA/MA（**5/10**）；",
         "- 日线由 60m 合成（近似 akshare 日线，夜盘≥20:30 归次一交易日）；",
         "- 后复权口径（DEC006 / 工程 _detect_and_splice 同款）；收益为收盘对收盘，",
         "  **非执行口径**；窗口重叠（逐日事件，另有 episode 首日对照）；",
         "- 引擎判定复用 rs017（=poolscan/pa.background 同款）；贴近阈值",
         "  max(0.5×ATR14, 0.5%×close) 为 MarketPullback 15m MA20 贴近的日线近似；",
         "- 机械判读阈值事前声明：背景增量/超额 **±0.3%**（+20日），支撑",
         "  反弹-破位差 **10pp**，样本门槛 **n≥30**。", ""]

    # ── 事件量概览 ──
    L += ["## 0. 事件量概览（扫描节点 = 品种×交易日，start=LOOKBACK+15）", "",
          "| 分组 | n | 说明 |", "|---|---|---|"]
    desc = {
        "T_NEAR": "趋势背景 + EMA20 贴近（生产 TrendPullback 触发形态）",
        "T_FAR": "趋势背景、未贴近（背景内非回调日）",
        "C_NEAR": "CHOP 日贴近（无趋势背景的回调形态）",
        "C_FAR": "CHOP 日未贴近",
    }
    for g in ("T_NEAR", "T_FAR", "C_NEAR", "C_FAR"):
        L.append(f"| {g} | {len(G[g])} | {desc[g]} |")
    L += [f"| 合计 | {len(recs)} | 全部交易日节点（raw 漂移基线） |", ""]

    # ── 1. 总体 2×2 ──
    L += md_table(
        "1. 总体：背景×回调 2×2 因子对照（+5/+10/+20 日方向调整收益，"
        "n/胜率/均值）",
        [("T_NEAR 趋势+贴近（逐日）", tn),
         ("T_NEAR episode 首日", ep),
         ("T_FAR 趋势+未贴近", tf),
         ("C_NEAR CHOP+贴近（raw 多头口径）", cn),
         ("C_FAR CHOP+未贴近（raw）", cf),
         ("ALL 全交易日（raw 漂移基线）", allr)],
        note="注：CHOP 无引擎方向，raw=多头口径，空头镜像=取负（机械对称）；"
             "T_NEAR/T_FAR 按 long 原值 / short 取负做方向调整。")

    # ── 2. 分品种 ──
    rows2 = []
    for s in SYMS:
        rows2.append((f"{s} T_NEAR", [r for r in tn if r["sym"] == s]))
        rows2.append((f"{s} C_NEAR(raw)", [r for r in cn if r["sym"] == s]))
    L += md_table("2. 分品种：趋势+贴近 vs CHOP+贴近", rows2)

    # ── 3. 分年 ──
    years = sorted({r["date"][:4] for r in tn + cn})
    rows3 = []
    for y in years:
        rows3.append((f"{y} T_NEAR", [r for r in tn if r["date"][:4] == y]))
        rows3.append((f"{y} C_NEAR(raw)", [r for r in cn if r["date"][:4] == y]))
    L += md_table("3. 分年度：趋势+贴近 vs CHOP+贴近", rows3)

    # ── 4. in/out 2022 ──
    L += md_table("4. in/out（2022 切分）",
                  [("T_NEAR in 2015-2021", [r for r in tn if r["date"] < SPLIT]),
                   ("T_NEAR out 2022-", [r for r in tn if r["date"] >= SPLIT]),
                   ("C_NEAR(raw) in", [r for r in cn if r["date"] < SPLIT]),
                   ("C_NEAR(raw) out", [r for r in cn if r["date"] >= SPLIT]),
                   ("ALL(raw) in", [r for r in allr if r["date"] < SPLIT]),
                   ("ALL(raw) out", [r for r in allr if r["date"] >= SPLIT])])

    # ── 5. 支撑/压力有效性（回踩不破 vs 破位，后 10 日）──
    def retest_rows(title):
        L2 = ["", f"## {title}", "",
              "| 口径 | n | 反弹/顺向率 | 破位率 | 守住未顺向率 | +10日均收益 |",
              "|---|---|---|---|---|---|"]

        def bucket(sub, label):
            if not sub:
                L2.append(f"| {label} | 0 | - | - | - | - |")
                return None
            nb = sum(1 for r in sub if r["brk"])
            fav = sum(1 for r in sub if not r["brk"] and ret(r, 10) > 0)
            L2.append(f"| {label} | {len(sub)} | {fav/len(sub):.1%} | "
                      f"{nb/len(sub):.1%} | "
                      f"{(len(sub)-nb-fav)/len(sub):.1%} | "
                      f"{mmean(sub, 10):+.2%} |")
            return (fav / len(sub), nb / len(sub), len(sub))

        out = {}
        longs = [r for r in recs if r["trend"] == "long"]
        shorts = [r for r in recs if r["trend"] == "short"]
        # 任务口径：收盘贴位（|close-位|≤1×ATR）
        lnear = [r for r in longs if r["lvl_dist"] <= RETEST_ATR * r["atr"]]
        snear = [r for r in shorts if r["lvl_dist"] <= RETEST_ATR * r["atr"]]
        lfar = [r for r in longs if r["lvl_dist"] > RETEST_ATR * r["atr"]]
        sfar = [r for r in shorts if r["lvl_dist"] > RETEST_ATR * r["atr"]]
        # 补充口径：日内极值触碰位区（日低 probe 支撑 / 日高 probe 压力）
        ltouch = [r for r in longs if r["lo"] <= r["sup"] + RETEST_ATR * r["atr"]]
        stouch = [r for r in shorts if r["hi"] >= r["res"] - RETEST_ATR * r["atr"]]
        out["strict"] = bucket(lnear, "BULL 回踩支撑（收盘≤1×ATR，任务口径）")
        out["touch_l"] = bucket(ltouch, "BULL 触碰支撑区（日低≤support+1×ATR）")
        out["far_l"] = bucket(lfar, "BULL 远离支撑（对照）")
        out["strict_s"] = bucket(snear, "BEAR 回踩压力（收盘≤1×ATR，任务口径）")
        out["touch_s"] = bucket(stouch, "BEAR 触碰压力区（日高≥pressure−1×ATR）")
        out["far_s"] = bucket(sfar, "BEAR 远离压力（对照）")
        both = lnear + snear
        tout = ltouch + stouch
        out["strict"] = bucket(both, "合并·任务口径回踩（收盘≤1×ATR）")
        out["touch"] = bucket(tout, "合并·触碰口径（日内极值触位区）")
        for s in SYMS:
            sub = [r for r in tout if r["sym"] == s]
            bucket(sub, f"合并·触碰 {s}")
        L2 += ["", "注：反弹/顺向=后 10 日未破位（close<support×0.98 或 "
                   ">pressure×1.02）且 +10 日收盘顺向；破位=10 日内任一收盘"
                   "穿越缓冲位；守住未顺向=其余。任务口径（收盘贴位）在日线"
                   "趋势状态下几乎不发生（见 n），有效性判读以触碰口径为准；"
                   "触碰=当日 low≤support+1×ATR / high≥pressure−1×ATR；"
                   "远离行为对照，其破位基准仍是同一位。"]
        return L2, out

    L5, rt = retest_rows(
        "5. 支撑/压力有效性：趋势日回踩/触碰位区后 10 日结局")
    L += L5

    # ── 6. RR 过滤价值 ──
    rows6 = [("rr≥1.5（生产放行）", [r for r in tn if r["rr"] >= RR_GATE]),
             ("rr<1.5（生产拦截）", [r for r in tn if r["rr"] < RR_GATE]),
             ("rr<2", [r for r in tn if r["rr"] < 2.0]),
             ("rr 2-3", [r for r in tn if 2.0 <= r["rr"] < 3.0]),
             ("rr≥3", [r for r in tn if r["rr"] >= 3.0])]
    L += md_table("6. RR 过滤价值：趋势+贴近事件按 rr 分桶（+20日为核心）",
                  rows6,
                  note="注：rr=0（risk≤0 退化事件）计入 <1.5/<2 桶。")

    # ── 近 10 个贴近事件（可核查样本）──
    last10 = sorted(tn, key=lambda r: r["date"])[-10:]
    L += ["", "## 诊断：最近 10 个 T_NEAR 事件（可核查样本）", "",
          "| 日期 | 品种 | 方向 | close | EMA20 | support | resistance | rr |"
          " +20日 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in last10:
        f20 = ret(r, 20)
        L.append(f"| {r['date']} | {r['sym']} | {r['trend']} | {r['c0']:.1f} | "
                 f"{r['e20']:.1f} | {r['sup']:.1f} | {r['res']:.1f} | "
                 f"{r['rr']:.2f} | " + (f"{f20:+.2%}" if f20 is not None else "-")
                 + " |")

    # ── 机械判读（阈值事前声明）──
    m_tn = mmean(tn, 20)
    m_ep = mmean(ep, 20)
    m_cn = mmean(cn, 20)
    m_all = mmean(allr, 20)
    bg = m_tn - m_cn if (m_tn is not None and m_cn is not None) else None
    ex = m_tn - m_all if (m_tn is not None and m_all is not None) else None
    L += ["", "## 7. 机械判读（阈值事前声明：±0.3% / 10pp）", ""]
    if ex is not None:
        if ex > BG_TH:
            L.append(f"- 超额（T_NEAR − ALL 基线，+20日）**{ex:+.2%} > +0.3%**"
                     f" → 回调+背景有超额收益")
        elif ex < -BG_TH:
            L.append(f"- 超额（T_NEAR − ALL 基线，+20日）**{ex:+.2%} < −0.3%**"
                     f" → 回调+背景为负超额（比不选还差）")
        else:
            L.append(f"- 超额（T_NEAR − ALL 基线，+20日）**{ex:+.2%} ≈ 0**"
                     f"（|·|≤0.3%）→ 回调买入无超额收益")
    if bg is not None:
        if bg > BG_TH:
            L.append(f"- 背景增量（T_NEAR − C_NEAR，+20日）**{bg:+.2%} > +0.3%**"
                     f" → **\"背景+回调\"组合成立**")
        elif bg > 0:
            L.append(f"- 背景增量 **{bg:+.2%}**（0<·≤0.3%）→ 弱增量，不足以覆盖成本")
        else:
            L.append(f"- 背景增量 **{bg:+.2%} ≤ 0** → **背景无增量**："
                     f"贴近形态本身不因趋势背景而变好")
    if ex is not None and ex <= BG_TH:
        L.append("- **日线 EMA20 回调 ≈0/负超额 → 与 MTG004 否决 EMA20_PULLBACK"
                 "（60m 触碰接刀）同构，入场触发需重构**")
    else:
        L.append("- 日线 EMA20 回调在趋势背景内呈正超额，与 MTG004（60m 无背景"
                 "闸门）不同构；背景闸门是关键差异")
    bp_s = rt.get("strict")
    bp_t = rt.get("touch")
    n_min = 30  # 机械判读样本门槛（事前声明）
    if bp_s and bp_s[2] >= n_min:
        bp, basis = bp_s, "任务口径·收盘贴位"
    elif bp_t and bp_t[2] >= n_min:
        bp, basis = bp_t, "补充口径·日内触碰"
    else:
        bp, basis = None, None
    if bp is None:
        L.append(f"- 支撑/压力有效性：任务口径 n={bp_s[2] if bp_s else 0}、"
                 f"触碰口径 n={bp_t[2] if bp_t else 0}，均 <{n_min} → "
                 f"**样本不足，无法判定**")
    else:
        fav_r, brk_r, nb = bp
        d_pp = fav_r - brk_r
        if d_pp >= PP_TH:
            L.append(f"- 支撑/压力（{basis}，n={nb}）：反弹率 {fav_r:.1%} vs "
                     f"破位率 {brk_r:.1%}（差 {d_pp:+.1%} ≥10pp）→ "
                     f"**位有一定有效性**")
        elif brk_r >= fav_r:
            L.append(f"- 支撑/压力（{basis}，n={nb}）：反弹率 {fav_r:.1%} vs "
                     f"破位率 {brk_r:.1%}（破位≥反弹）→ **位无有效性"
                     f"（形式参数）**")
        else:
            L.append(f"- 支撑/压力（{basis}，n={nb}）：反弹率 {fav_r:.1%} vs "
                     f"破位率 {brk_r:.1%}（差 {d_pp:+.1%} <10pp）→ 中性偏弱")
    tl, tsl, fl, fs = (rt.get("touch_l"), rt.get("touch_s"),
                       rt.get("far_l"), rt.get("far_s"))
    if tl and fl:
        note = (f"- 注（判读局限）：BULL 触碰后顺向率 {tl[0]:.1%} vs 远离对照 "
                f"{fl[0]:.1%}，未做随机位（placebo）对照，不能证明摆动点位"
                f"优于任意位；破位率低部分是缓冲带（×0.98/×1.02）效应")
        if tsl and fs:
            note += (f"；BEAR 触碰后顺向率 {tsl[0]:.1%} vs 远离对照 {fs[0]:.1%}"
                     + ("（不占优）→ 压力位有效性弱于支撑位" if tsl[0] <= fs[0]
                        else "（占优）"))
        L.append(note + "。")
    bl2 = mmean([r for r in tn if r["rr"] < 2.0], 20)
    b23 = mmean([r for r in tn if 2.0 <= r["rr"] < 3.0], 20)
    b3 = mmean([r for r in tn if r["rr"] >= 3.0], 20)
    if None not in (bl2, b23, b3):
        if b3 > b23 > bl2:
            L.append(f"- RR 分桶 +20日：<2 {bl2:+.2%} / 2-3 {b23:+.2%} / ≥3 "
                     f"{b3:+.2%} 单调上升 → **RR 有筛选价值**")
        elif b3 <= bl2:
            L.append(f"- RR 分桶 +20日：<2 {bl2:+.2%} / 2-3 {b23:+.2%} / ≥3 "
                     f"{b3:+.2%}，高 RR 不更优 → **RR≥1.5 闸门未筛出更高质量"
                     f"入场（结构参数近似无效）**")
        else:
            L.append(f"- RR 分桶 +20日：<2 {bl2:+.2%} / 2-3 {b23:+.2%} / ≥3 "
                     f"{b3:+.2%} 非单调 → 混合，RR 闸门价值存疑")
    L += ["", "## 8. 诚实声明", "",
          "- 子集：5/10（RB/CU/M/TA/MA），结论不外推全池；",
          "- 日线由 60m 合成（近似口径）；后复权（DEC006）；",
          "- 收益为事件日收盘对 +N 日收盘的方向调整值，非执行口径、无成本；",
          "- 窗口重叠（逐日事件），episode 首日口径仅列总体行作对照；",
          "- 贴近/回踩阈值为日线近似（生产为 15m MA20 贴近 + 60m 引擎），"
          "量级结论可参考，精确触发需以生产周期复验；",
          "- **任务口径回踩（收盘贴位且处趋势状态）在日线上几乎不发生**"
          "（合并 n=6 / 16126 节点）——这本身是审计发现：生产 TrendPullback "
          "入选时支撑/压力通常远离现价（risk 分母大、rr 被压低，与 79% 事件 "
          "rr<1.5 一致）；支撑/压力有效性判读依赖触碰口径补充（n 见第 5 节），"
          "其口径宽于任务定义；",
          "- 机械判读为阈值化规则输出，不构成启用/退役决定，决定权在 MTG。"]

    out = OUT / "pullback_rr.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)

    # ── 控制台关键数字 ──
    print("\n===== RS019 环节2 关键数字 =====")
    print(f"扫描节点={len(recs)}  T_NEAR={len(tn)} (ep={len(ep)})  "
          f"T_FAR={len(tf)}  C_NEAR={len(cn)}  C_FAR={len(cf)}")
    for name, sub in [("T_NEAR", tn), ("T_NEAR_ep", ep), ("C_NEAR", cn),
                      ("ALL", allr)]:
        n, w, m = srat(sub, 20)
        print(f"{name:>9} +20日 n={n} win={w:.1%} avg={m:+.2%}")
    if ex is not None:
        print(f"超额(T_NEAR-ALL,+20d)={ex:+.2%}  背景增量(T_NEAR-C_NEAR)="
              f"{bg:+.2%}")
    if bp:
        print(f"支撑/压力（{basis} n={bp[2]}）：反弹率={bp[0]:.1%} "
              f"破位率={bp[1]:.1%}")
    print(f"RR 闸门：放行 {mmean([r for r in tn if r['rr'] >= RR_GATE], 20):+.2%}"
          f" / 拦截 {mmean([r for r in tn if r['rr'] < RR_GATE], 20):+.2%}"
          f"（+20日均）")
    print(f"RR 分桶：<2 {bl2:+.2%} / 2-3 {b23:+.2%} / ≥3 {b3:+.2%}")


if __name__ == "__main__":
    main()
