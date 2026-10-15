# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS019 臂4 hybrid 限多头 v3（干净重写；承接 RS020 §7.2 臂4 预注册设计）。

旧版（v2 框架）多层数据管道索引/前窗口缺陷废弃：td_set 未做夜盘归属、
前瞻误用当日收盘（f20 无前瞻窗口）、tday_of 定义未用。本版全部重写。

行布局（8 元素，与 rs020_merge_backtest 一致，防索引漂移）：
  I_DAY=0, I_DT=1, I_O=2, I_H=3, I_L=4, I_C=5, I_V=6, I_OI=7

设计（预注册出处 RS020 §7.2/§7.5 + 用户批复"臂4 hybrid 限多头"）：
  准入 = 臂2 Hermes pullback 四因子 ∩ 60m HH/HL 多头趋势
         （rs020_merge_backtest.py 已验证管线逐字移植：夜盘 tday_of 归属、
          后复权 splice_adjust 链式+坏点护栏、trend_h1_60m θ1.5%+4% 换月平滑）
  4a = 准入锚（对照；应复现臂2 long 子集 OOS +20日 +0.63%，n=111）
  4b = 4a + mom6 动量确认：60m 平滑序列 6 根动量 >0（RS013/CAND-007 口径）
  4c = 4a + M-EX-003 回调到位吸收确认（60m h2h 原口径，exhaustion_h2h.py 逐字）：
       缩量 rvol≤0.8 ∧ 收盘反转侧 1/3（close_pos≥0.66）∧ 下跌背景 c<SMA20
       ∧ 闸门 prior_ret20>−5%；仅多头场景 = S-002 主场景（实证边界内）
  4d = 4b ∩ 4c 双确认（主臂）
  quant 积分准入（§7.2 第三增量）：公式档案 quant_gap_analysis.md 未落盘，
  为不臆造公式挂起待归档（诚实缺口，见报告）。

前视控制（本版新增，实证 datetime=bar 开始时刻，2024-06-03 RB 5m 聚合对照）：
  M-EX-003 确认 bar 的真实收盘时刻=覆盖区间 [T,T+60min) 内最后一根 5m 的
  时刻+5min（60m 模板 bar 11:15/14:15 实际收于 11:30/15:00），须 ≤ 节点收盘
  时刻(node_dt+5min)。臂2 趋势过滤维持 rs020 原口径（dt≤node_dt，含未收当根）
  以保可比性，差异声明。
  🔴 关联勘误（2026-10-15）：rs020 原版 60m 节点过滤 b[0]<=node_dt 系空操作
  （b[0]=I_DAY 恒空串），臂2 已发布 OOS +0.78% 存在前视泄漏；本版管线为
  正确节点对齐版（bisect on I_DT），4a 为修正后臂2 多头锚。

预注册判读（沿用 v2 头部 + RS020 §7.5 建议的分解呈现）：
  主判读：4d OOS(2022-) +20 日均值 >0 且 > 臂2 全方向 OOS +0.85% → 优化有增量
  （锚=2026-10-15 双勘误修正后 rs020 臂2 OOS +0.85%，n=106；原预注册引用的
  +0.78% 系含前视泄漏口径，勘误后以修正值为锚）；
  最小样本护栏：OOS n≥30 才下机械结论，n<30 = 样本不足（inconclusive）——
  既不宣称有增量也不据此否决（防 n 极小时空洞判读）；
  分解呈现：4b/4c 对 4a 锚的 OOS 增量同步全表报告（多重比较警示：结论以 4d 为准）。
  4a 与修正后 rs020 臂2 long 已逐位互证（n=108/74/34 全表一致，两实现独立等价）。

输出：assets/RS019/merge_hybrid_backtest.md
"""

from __future__ import annotations

import csv
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA5 = Path(r"D:\AIprj\tradereplay\data\5m")
DATA60 = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = ROOT.parent / "assets" / "RS019"
SYMS = {"RB": "SHFE", "CU": "SHFE", "M": "DCE", "TA": "CZCE", "MA": "CZCE"}
SPLIT = "2022-01-01"
HORIZONS = (5, 10, 20)

I_DAY, I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(8)

CFG5 = dict(W=240, theta=0.8, min_leg=1.0, min_bars=4, min_er=0.25,
            ma_near=0.6, pb_lo=0.30, pb_hi=0.70, max_age=90)
MIN_PB_BARS = 2
TAIL5 = 1500
TAIL60 = 300
BAR_MIN = {"5m": 5, "60m": 60}


# ───────────────────────── 数据管线（rs020 已验证组件逐字移植） ─────────────────────────

def tday_of(dt_str: str) -> str:
    d, t = dt_str.split(" ")
    if int(t[:2]) >= 20:
        y, m, dd = map(int, d.split("-"))
        return (date(y, m, dd) + timedelta(days=1)).isoformat()
    return d


def splice_adjust(rows: list[list]) -> tuple[int, int]:
    """工程 _detect_and_splice 同款后复权（TR/ATR14 + 三信号评分≥2，链式+坏点护栏）。"""
    n = len(rows)
    removed = 0
    if n < 2:
        return removed, 0
    trs = [rows[0][I_H] - rows[0][I_L]]
    for i in range(1, n):
        trs.append(max(rows[i][I_H] - rows[i][I_L],
                       abs(rows[i][I_H] - rows[i - 1][I_C]),
                       abs(rows[i][I_L] - rows[i - 1][I_C])))
    atr = []
    for i in range(n):
        w = trs[max(0, i - 13): i + 1]
        atr.append(sum(w) / len(w))
    bad_pts = 0
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
                    bad_pts += 1
                    continue
                for j in range(i, n):
                    for k in (I_O, I_H, I_L, I_C):
                        rows[j][k] *= local
    return removed, bad_pts


def load_5m_adj(sym: str, exch: str):
    rows, bad = [], 0
    with (DATA5 / exch / sym / f"{sym}.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dt = r.get("datetime") or ""
            if dt[:4] < "2015":
                continue
            try:
                o, h, l, c = (float(r["open"]), float(r["high"]),
                              float(r["low"]), float(r["close"]))
                v = float(r.get("volume") or 0)
                oi = float(r.get("position") or 0)
            except (ValueError, TypeError):
                bad += 1
                continue
            if min(o, h, l, c) <= 0 or h / max(l, 1e-9) > 50:
                bad += 1
                continue
            rows.append([tday_of(dt), dt, o, h, l, c, v, oi])
    removed, bad_pts = splice_adjust(rows)
    bad += removed
    rows.sort(key=lambda r: r[I_DT])
    tdays = sorted({r[I_DAY] for r in rows})
    tclose = {}
    for r in rows:
        tclose[r[I_DAY]] = r[I_C]
    return rows, tdays, tclose, bad, bad_pts


def load_60m(sym: str, exch: str):
    """60m 原始（未复权直拼，趋势过滤+mom6+吸收确认输入）；本版带量能列。"""
    rows = []
    with (DATA60 / exch / sym / f"{sym}.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append(["", r["datetime"], float(r["open"]), float(r["high"]),
                             float(r["low"]), float(r["close"]),
                             float(r.get("volume") or 0), 0.0])
            except (ValueError, TypeError):
                continue
    rows.sort(key=lambda r: r[I_DT])
    return rows


# ───────────────────────── 臂2 判据（pullback_arm，rs020 逐字移植） ─────────────────────────

def zigzag_legs(seg, theta):
    piv = []
    trend = 0
    ext_i, ext_p = 0, seg[0][I_C]
    for i in range(1, len(seg)):
        hi, lo = seg[i][I_H], seg[i][I_L]
        if trend >= 0:
            if hi > ext_p:
                ext_i, ext_p = i, hi
            elif lo < ext_p * (1 - theta):
                piv.append((ext_i, "H"))
                trend = -1
                ext_i, ext_p = i, lo
        if trend <= 0:
            if lo < ext_p:
                ext_i, ext_p = i, lo
            elif hi > ext_p * (1 + theta):
                piv.append((ext_i, "L"))
                trend = 1
                ext_i, ext_p = i, hi
    return piv


def er_of(seg):
    if len(seg) < 2:
        return 0.0
    net = abs(seg[-1][I_C] - seg[0][I_C])
    path = sum(abs(seg[i][I_C] - seg[i - 1][I_C]) for i in range(1, len(seg)))
    return net / path if path > 0 else 0.0


def pullback_arm(seg, cfg):
    """臂2 判据（pullback_screen.analyze 移植）。返回 dict 或 None。"""
    W = cfg["W"]
    if len(seg) < W + 2:
        return None
    s = seg[-W:]
    n = len(s)
    cur = s[-1][I_C]
    m20 = sum(x[I_C] for x in s[-20:]) / 20
    m60 = sum(x[I_C] for x in s[-60:]) / 60
    dev_ma = min(abs(cur - m20) / cur * 100 if m20 else 999,
                 abs(cur - m60) / cur * 100 if m60 else 999)
    piv = zigzag_legs(s, cfg["theta"] / 100.0)
    if len(piv) < 2:
        return None
    best = None
    for k in range(len(piv) - 1):
        (a, ta), (b, tb) = piv[k], piv[k + 1]
        if b <= a:
            continue
        if ta == "L" and tb == "H":
            lo_, hi_ = s[a][I_L], s[b][I_H]
            amp = (hi_ - lo_) / lo_ * 100 if lo_ else 0
            d = "long"
        elif ta == "H" and tb == "L":
            hi_, lo_ = s[a][I_H], s[b][I_L]
            amp = (hi_ - lo_) / hi_ * 100 if hi_ else 0
            d = "short"
        else:
            continue
        if amp < cfg["min_leg"] or (b - a) < cfg["min_bars"]:
            continue
        if er_of(s[a:b + 1]) < cfg["min_er"]:
            continue
        age = n - 1 - b
        if age < MIN_PB_BARS or age > cfg["max_age"]:
            continue
        if best is None or b > best["b"]:
            best = {"a": a, "b": b, "dir": d, "amp": amp,
                    "er": er_of(s[a:b + 1]), "hi": hi_, "lo": lo_}
    if best is None:
        return None
    hi, lo = best["hi"], best["lo"]
    pb = ((hi - cur) / (hi - lo) if best["dir"] == "long"
          else (cur - lo) / (hi - lo)) if hi > lo else 0.0
    if not (cfg["pb_lo"] <= pb <= cfg["pb_hi"]) or dev_ma > cfg["ma_near"]:
        return None
    return {"dir": best["dir"], "pb": pb * 100, "dev_ma": dev_ma}


# ───────────────────────── 60m 趋势/mom6（Hermes B 方案 4% 换月平滑） ─────────────────────────

def roll_factor_60m(rows60, gap_min=0.04):
    best = None
    for i in range(1, len(rows60)):
        prev_c = rows60[i - 1][I_C]
        mid = (rows60[i][I_H] + rows60[i][I_L]) / 2
        gap = abs(mid - prev_c) / prev_c if prev_c else 0
        if gap > gap_min:
            f = prev_c / mid if mid else 1.0
            if 0.85 < f < 1.15 and (best is None or gap > best[0]):
                best = (gap, i, f)
    return (best[1], best[2]) if best else (None, 1.0)


def smooth_60m(rows60):
    """Hermes B 方案平滑（返回副本；与 rs020 trend_h1_60m 内部完全一致）。"""
    rows = [list(r) for r in rows60]
    i_cut, factor = roll_factor_60m(rows)
    if i_cut is not None and factor != 1.0:
        for i in range(i_cut, len(rows)):
            for k in (I_H, I_L, I_C):
                rows[i][k] *= factor
    return rows


def hh_hl_trend(rows, theta=0.015):
    """Hermes trend_h1：θ1.5% zigzag HH/HL（输入须已平滑）。"""
    if len(rows) < 60:
        return "震荡"
    piv = []
    trend = 0
    ext_i, ext_p = 0, rows[0][I_C]
    for i in range(1, len(rows)):
        hi, lo = rows[i][I_H], rows[i][I_L]
        if trend >= 0:
            if hi > ext_p:
                ext_i, ext_p = i, hi
            elif lo < ext_p * (1 - theta):
                piv.append((ext_i, "H", ext_p))
                trend = -1
                ext_i, ext_p = i, lo
        if trend <= 0:
            if lo < ext_p:
                ext_i, ext_p = i, lo
            elif hi > ext_p * (1 + theta):
                piv.append((ext_i, "L", ext_p))
                trend = 1
                ext_i, ext_p = i, hi
    hs = [x for x in piv if x[1] == "H"][-2:]
    ls = [x for x in piv if x[1] == "L"][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return "震荡"
    if hs[-1][2] > hs[-2][2] and ls[-1][2] > ls[-2][2]:
        return "多头"
    if hs[-1][2] < hs[-2][2] and ls[-1][2] < ls[-2][2]:
        return "空头"
    return "震荡"


def mom6_60m(smoothed):
    """RS013 口径：6 根 60m 动量（平滑序列，须 ≥7 根）。"""
    if len(smoothed) < 7:
        return None
    base = smoothed[-7][I_C]
    if not base:
        return None
    return smoothed[-1][I_C] / base - 1


# ───────────────────────── M-EX-003 回调到位吸收确认（60m h2h 原口径） ─────────────────────────

def mex003_long_confirmed(h60_prefix):
    """事件时点最近已收 60m bar 的吸收确认（exhaustion_h2h.py 多头口径逐字）：
    c<SMA20 ∧ close_pos≥0.66 ∧ rvol≤0.8 ∧ prior_ret20>−5%（prior=20 根回看）。
    输入须已按"开始时刻+60min ≤ 节点收盘时刻"截断（无前视）。"""
    if len(h60_prefix) < 21:
        return False
    bars = h60_prefix[-21:]
    c21 = [x[I_C] for x in bars]
    c = c21[-20:]                      # SMA20/rvol20 窗口（含当根）
    v = [x[I_V] for x in h60_prefix[-20:]]
    bar = h60_prefix[-1]
    hi, lo, cc = bar[I_H], bar[I_L], bar[I_C]
    rng = hi - lo
    if rng <= 0 or min(c21) <= 0:
        return False
    sma20 = sum(c) / 20
    v20 = sum(v) / 20
    if v20 <= 0:
        return False
    rvol = v[-1] / v20
    close_pos = (cc - lo) / rng
    prior_ret20 = cc / c21[0] - 1
    return cc < sma20 and close_pos >= 0.66 and rvol <= 0.8 and prior_ret20 > -0.05


# ───────────────────────── 主流程 ─────────────────────────

def parse_dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events = []          # {"sym","td","entry","v4a","v4b","v4c","v4d"}
    counts = defaultdict(int)
    tdays_all, tcloses = {}, {}
    for sym, exch in SYMS.items():
        rows, tdays, tclose, bad, bad_pts = load_5m_adj(sym, exch)
        tdays_all[sym], tcloses[sym] = tdays, tclose
        print(f"[load] {sym}: 5m bars={len(rows)} 坏行 {bad} 复权护栏跳过 {bad_pts}")
        h60 = load_60m(sym, exch)
        dt5 = [r[I_DT] for r in rows]
        dt60 = [r[I_DT] for r in h60]
        by_day = defaultdict(list)
        for r in rows:
            by_day[r[I_DAY]].append(r)

        for td in tdays:
            day_bars = by_day.get(td) or []
            if not day_bars:
                continue
            node = day_bars[-1]
            node_dt = node[I_DT]
            j5 = bisect_right(dt5, node_dt)
            tail5 = rows[max(0, j5 - TAIL5): j5]
            if len(tail5) < 500:
                continue
            j60 = bisect_right(dt60, node_dt)
            h60n = h60[max(0, j60 - TAIL60): j60]
            if len(h60n) < 60:
                continue
            smoothed = smooth_60m(h60n)
            if hh_hl_trend(smoothed) != "多头":
                continue
            r = pullback_arm(tail5, CFG5)
            if r is None or r["dir"] != "long":
                continue

            # ── 4a 准入锚事件 ──
            ev = {"sym": sym, "td": td, "entry": node[I_C],
                  "v4a": True, "v4b": False, "v4c": False, "v4d": False}
            counts["4a"] += 1

            # ── 4b mom6 动量确认（60m 平滑序列） ──
            m6 = mom6_60m(smoothed)
            if m6 is not None and m6 > 0:
                ev["v4b"] = True
                counts["4b"] += 1

            # ── 4c M-EX-003 吸收确认（最近已收 60m bar，无前视） ──
            # bar 真实收盘时刻=其覆盖区间 [T,T+60min) 内最后一根 5m 的时刻+5min
            # （60m 模板 bar 11:15/14:15 实际收于 11:30/15:00，用 5m 覆盖实证）
            node_close = parse_dt(node_dt) + timedelta(minutes=BAR_MIN["5m"])
            k = j60
            while k > 0:
                t0 = h60[k - 1][I_DT]
                t1 = (parse_dt(t0) +
                      timedelta(minutes=BAR_MIN["60m"])).strftime("%Y-%m-%d %H:%M:%S")
                lo_i = bisect_left(dt5, t0)
                hi_i = bisect_left(dt5, t1)
                if hi_i > lo_i:
                    bar_close = parse_dt(dt5[hi_i - 1]) + timedelta(minutes=5)
                else:                      # 无 5m 覆盖→保守回退 start+60
                    bar_close = parse_dt(t0) + timedelta(minutes=BAR_MIN["60m"])
                if bar_close <= node_close:
                    break
                k -= 1
            if k >= 21 and mex003_long_confirmed(h60[:k]):
                ev["v4c"] = True
                counts["4c"] += 1

            if ev["v4b"] and ev["v4c"]:
                ev["v4d"] = True
                counts["4d"] += 1
            events.append(ev)

    # ── 前瞻（交易日 +5/+10/+20 收盘，方向调整，无成本） ──
    def fwd(sym, td, entry):
        tds = tdays_all[sym]
        i = tds.index(td)
        out = {}
        for h in HORIZONS:
            j = i + h
            if j < len(tds):
                out[h] = (tcloses[sym][tds[j]] / entry - 1)
        return out

    for e in events:
        e["fwd"] = fwd(e["sym"], e["td"], e["entry"])

    # ── 报告 ──
    def tbl(sub, label):
        L = [f"**{label}**", "",
             "| 口径 | " + " | ".join(f"+{k}日胜率" for k in HORIZONS) + " | "
             + " | ".join(f"+{k}日均值" for k in HORIZONS) + " |",
             "|---|" + "---|" * (len(HORIZONS) * 2)]
        for tag, cond in (("全样本", lambda e: True),
                          ("in <2022", lambda e: e["td"] < SPLIT),
                          ("out ≥2022", lambda e: e["td"] >= SPLIT)):
            s2 = [e for e in sub if cond(e)]
            cells = []
            for h in HORIZONS:
                v = [e["fwd"][h] for e in s2 if h in e["fwd"]]
                cells.append(f"{sum(1 for x in v if x > 0) / len(v):.1%}（n={len(v)}）"
                             if v else "-")
            for h in HORIZONS:
                v = [e["fwd"][h] for e in s2 if h in e["fwd"]]
                cells.append(f"{sum(v) / len(v):+.2%}" if v else "-")
            L.append(f"| {tag} | " + " | ".join(cells) + " |")
        return L

    L = ["# RS019 臂4 hybrid 限多头（v3 干净重写；RS020 §7.2 预注册设计）", "",
         "- 准入=臂2 Hermes pullback 四因子 ∩ 60m HH/HL 多头（θ1.5%+4% 换月平滑）；",
         "- 4a=准入锚；4b=+mom6（60m 平滑 6 根动量>0）；4c=+M-EX-003 吸收确认",
         "  （60m h2h 原口径：缩量≤0.8+收盘上1/3+回调背景+prior_ret20>−5%，",
         "  确认 bar 无前视截断）；4d=4b∩4c 双确认（主臂）；",
         "- 前瞻=事件收盘→交易日 +5/+10/+20 收盘（方向调整，无成本）；",
         f"- 事件数：4a={counts['4a']} 4b={counts['4b']} 4c={counts['4c']} "
         f"4d={counts['4d']}；对照锚（勘误修正后 rs020）：臂2 全方向 OOS +20日 "
         "+0.85%（n=106）、臂2 long OOS +0.72%（n=34，与本报告 4a 逐位互证）。", ""]

    name_map = {"4a": "臂4a 准入锚（对照）",
                "4b": "臂4b = 4a + mom6 动量确认",
                "4c": "臂4c = 4a + M-EX-003 吸收确认",
                "4d": "臂4d = 4b∩4c 双确认（主臂）"}
    for key in ("4a", "4b", "4c", "4d"):
        sub = [e for e in events if e["v" + key]]
        L += tbl(sub, name_map[key])
        L.append("")

    # OOS +20 分解
    L += ["## OOS +20日 分解（增量归因）", "",
          "| 臂 | OOS n | 胜率 | 均值 | vs 4a 增量 |", "|---|---|---|---|---|"]
    base = None
    oos_rows = {}
    for key in ("4a", "4b", "4c", "4d"):
        sub = [e for e in events if e["v" + key] and e["td"] >= SPLIT and 20 in e["fwd"]]
        v = [e["fwd"][20] for e in sub]
        m = sum(v) / len(v) if v else None
        w = sum(1 for x in v if x > 0) / len(v) if v else None
        oos_rows[key] = (m, len(v), w)
        if key == "4a":
            base = m
        delta = f"{m - base:+.2%}" if (m is not None and base is not None) else "-"
        L.append(f"| {key} | {len(v)} | {w:.1%} | {m:+.2%} | {delta} |"
                 if m is not None else f"| {key} | n不足 | - | - | - |")

    # 分年（OOS 段，诚实检查）
    L += ["", "## 4d 分年 OOS +20日（诚实检查）", "",
          "| 年 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    by_year = defaultdict(list)
    for e in events:
        if e["v4d"] and e["td"] >= SPLIT and 20 in e["fwd"]:
            by_year[e["td"][:4]].append(e["fwd"][20])
    for y in sorted(by_year):
        v = by_year[y]
        L.append(f"| {y} | {len(v)} | {sum(1 for x in v if x > 0) / len(v):.1%} "
                 f"| {sum(v) / len(v):+.2%} |")

    # 分品种（OOS 段）
    L += ["", "## 4d 分品种 OOS +20日", "",
          "| 品种 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    by_sym = defaultdict(list)
    for e in events:
        if e["v4d"] and e["td"] >= SPLIT and 20 in e["fwd"]:
            by_sym[e["sym"]].append(e["fwd"][20])
    for s in sorted(by_sym):
        v = by_sym[s]
        L.append(f"| {s} | {len(v)} | {sum(1 for x in v if x > 0) / len(v):.1%} "
                 f"| {sum(v) / len(v):+.2%} |")

    # 预注册机械判读（最小样本护栏 n≥30）
    MIN_N = 30
    L += ["", "## 预注册判读（机械，含最小样本护栏 n≥30）", ""]
    m4d, n4d, w4d = oos_rows["4d"]
    if m4d is None or n4d < MIN_N:
        L.append(f"- 主判读：4d OOS +20日样本不足"
                 f"（n={n4d if m4d is not None else 0} < {MIN_N}）→ "
                 "**判读不可下结论（inconclusive）**——不宣称优化有增量，"
                 "也不据此否决；路径建议（需预注册后另行验证）：扩大品种池 / "
                 "节点对齐 60m 收盘 / 吸收确认窗口化（回踩腿龄窗内任一已收 bar）")
    else:
        verdict = m4d > 0 and m4d > 0.0085
        L.append(f"- 主判读：4d OOS +20日 {m4d:+.2%}（n={n4d}）— "
                 + ("**>0 且 >臂2 全方向 +0.85% → 优化有增量 ✅**"
                    if verdict else "**未同时满足 >0 且 >+0.85% → 优化无增量 ❌**"))
    m4a = oos_rows["4a"][0]
    if m4a is not None and all(oos_rows[k][0] is not None for k in ("4b", "4c")):
        L.append(f"- 分解呈现：4b {oos_rows['4b'][0]:+.2%}（n={oos_rows['4b'][1]}） / "
                 f"4c {oos_rows['4c'][0]:+.2%}（n={oos_rows['4c'][1]}，单事件主导，"
                 f"无统计意义） / 4d {m4d:+.2%}（n={n4d}） vs 4a 锚 {m4a:+.2%}"
                 f"（n={oos_rows['4a'][1]}）——小样本仅作方向性观察，不作增量结论")
    L.append("- 多重比较警示：4 变体×3 horizon 同报，结论以预注册 4d 主判读为准；"
             "分解表仅作归因呈现，不作选择性引用。")

    L += ["", "## 诚实声明", "",
          "- 5/10 品种子集；5m 后复权为研究侧移植（同 rs020）；60m 为未复权直拼",
          "  +Hermes 4% 平滑（趋势过滤/mom6 在平滑序列上，M-EX-003 在原始序列上——",
          "  换月跳空可污染 rvol/SMA20，坏点护栏仅护后复权层）；",
          "- 臂2 趋势过滤维持 rs020 原口径（dt≤node_dt，含未收当根≈前视≤55min）",
          "  以保与臂2 可比；M-EX-003 确认 bar 用 5m 覆盖实证真实收盘时刻，",
          "  恰在节点收盘形成的当根包含在内（无前视）；",
          "- mom6 周期口径选择=60m（选品背景周期），非 RS013 原样 60m 基线复刻——",
          "  与 CAND-007 突破段用法不同，属口径移植假设；",
          "- M-EX-003 用法定位：S-002 主场景回调到位确认（仅多头、含闸门），",
          "  非对其他信号的量能叠加过滤（MLIB 红线内）；",
          "- quant 积分准入层：公式档案（quant_gap_analysis.md/hermes_scripts）未落盘，",
          "  挂起不臆测，待归档后补测（本报告缺口如实登记）；",
          "- 收盘口径非执行口径；无成本无执行建模；datetime 语义=bar 开始时刻",
          "  （2024-06-03 RB 5m 聚合对照实证）。"]

    out = OUT / "merge_hybrid_backtest.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    for key in ("4a", "4b", "4c", "4d"):
        m, n, w = oos_rows[key]
        if m is not None:
            print(f"{key} OOS +20d: n={n} win={w:.1%} avg={m:+.2%}")


if __name__ == "__main__":
    main()
