# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS020 合并选品对照回测（goal-86fa51d9；合并设计 v2 = RS020 §7）。

🔴 勘误（2026-10-15，两处）：
①原版 §main 臂2 节点过滤 `b[0] <= node_dt` 用错索引（60m 行布局 b[0]=I_DAY
  恒空串→过滤恒真），全部历史节点都用了数据集末端的最后 300 根 60m 做趋势
  判定=前视泄漏，已发布的臂2 OOS +0.78% 不可靠；臂3（flats）不经 60m 过滤、
  不受影响。本版修正为 b[I_DT]。
②原版 trend_h1_60m 对 rows60[-300:] 浅拷贝后原地平滑乘法，跨节点变异共享行
  （链式残留+人工跳变）。本版改深拷贝。
修正后数字以 assets/RS020/merge_backtest.md 新版为准（勘误记录见 STATUS）。

行布局常量（全脚本统一，防索引漂移）：
  I_DAY=0, I_DT=1, I_O=2, I_H=3, I_L=4, I_C=5, I_V=6, I_OI=7

臂2（Hermes pullback_screen 移植，全判据原参数）：
  5m 尾 1500 根窗内：zigzag θ0.8%（h/l 极值比例确认）→ 最显著腿（幅≥1.0%、
  ≥4根、ER≥0.25、腿龄 2~90 根）→ 回踩 30–70% → MA 贴近 ≤0.6% → 四因子打分；
  60m 趋势过滤：trend_h1（θ1.5%、尾 300 根、Hermes 4% 换月平滑 B 方案）方向
  一致。评估节点=每交易日最后一根 5m。
臂3（Hermes flats_scan_5m 移植，find_flats_v5 原参数）：
  5m 全序列滚动箱体：local_compress(16)<0.65（stride=4 近似）→ 分段 →
  收盘 P10–P90 实体带 + 带宽 <1% + 斜率 t<4 + 双侧触及 ≥2 + 段尾 3 根内
  （is_current）→ 边缘触碰候选（≤下带+15%带宽→long；≥上带−15%→short）。
数据：5m 全历史后复权（工程 _detect_and_splice 同款移植，坏点护栏）——
  对生产为偏差修正（生产 5m zigzag 未做换月平滑，MA2609→2701 −9.3% 案例在档）；
  60m 趋势过滤输入=原始 60m + Hermes 4% 平滑（忠实臂2 生产口径）。

统一度量：事件收盘→交易日 +5/+10/+20 收盘，方向调整，无成本。
预注册判读：臂2/3 任一 OOS(2022-) +20 日均值 >0 且 > 臂1（−0.54%，RS019）
→ 合并方向成立（臂4 hybrid 深化）；全负 → 选品层重构转 RS001 三因子直接建模。

输出：assets/RS020/merge_backtest.md
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA5 = Path(r"D:\AIprj\tradereplay\data\5m")
DATA60 = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = ROOT.parent / "assets" / "RS020"
SYMS = {"RB": "SHFE", "CU": "SHFE", "M": "DCE", "TA": "CZCE", "MA": "CZCE"}
SPLIT = "2022-01-01"
HORIZONS = (5, 10, 20)

I_DAY, I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(8)

CFG5 = dict(W=240, theta=0.8, min_leg=1.0, min_bars=4, min_er=0.25,
            ma_near=0.6, pb_lo=0.30, pb_hi=0.70, max_age=90)
MIN_PB_BARS = 2
FLAT = dict(window=16, compress=0.65, gap_allow=6, band_max=1.0,
            slope_t_max=4.0, touch=2, tail_margin=3)
STRIDE = 4


def tday_of(dt_str: str) -> str:
    d, t = dt_str.split(" ")
    if int(t[:2]) >= 20:
        y, m, dd = map(int, d.split("-"))
        return (date(y, m, dd) + timedelta(days=1)).isoformat()
    return d


def splice_adjust(rows: list[list]) -> tuple[int, int]:
    """工程 _detect_and_splice 同款后复权（TR/ATR14 + 三信号评分≥2，链式）。
    返回 (剔除坏bar数, 跳过的坏复权点数)。"""
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
    ratio = 1.0
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
                ratio *= local
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


def load_60m_raw(sym: str, exch: str):
    rows = []
    with (DATA60 / exch / sym / f"{sym}.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append(["", r["datetime"], float(r["open"]), float(r["high"]),
                             float(r["low"]), float(r["close"]), 0.0, 0.0])
            except (ValueError, TypeError):
                continue
    rows.sort(key=lambda r: r[I_DT])
    return rows


def sma_last(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def zigzag_legs(seg, theta):
    """pullback_screen 同款：h/l 极值比例确认摆动点。seg 行布局同主常量。"""
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
    s_amp = min(20, best["amp"] / (cfg["min_leg"] * 3) * 20)
    s_er = min(20, max(0, (best["er"] - cfg["min_er"]) / (1 - cfg["min_er"]) * 20))
    s_pb = max(0, 30 - abs(pb - 0.5) / 0.2 * 30)
    s_ma = max(0, 30 - dev_ma / cfg["ma_near"] * 30)
    return {"dir": best["dir"], "score": s_amp + s_er + s_pb + s_ma,
            "leg_amp": best["amp"], "er": best["er"], "pb": pb * 100,
            "dev_ma": dev_ma}


def roll_factor_60m(rows60, gap_min=0.04):
    """Hermes B 方案：|bar中值−前收|>4% 的唯一最大者 = 切换bar。"""
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


def trend_h1_60m(rows60):
    """Hermes trend_h1：θ1.5% zigzag HH/HL（尾 300 根，含 4% 换月平滑）。
    🔴 勘误2（2026-10-15）：rows60[-300:] 仅外层拷贝、内层行共享，平滑乘法原地
    变异会跨节点链式残留并制造人工跳变——改为深拷贝（语义=每节点独立平滑）。"""
    rows = [list(r) for r in rows60[-300:]]
    if len(rows) < 60:
        return "震荡"
    i_cut, factor = roll_factor_60m(rows)
    if i_cut is not None and factor != 1.0:
        for i in range(i_cut, len(rows)):
            for k in (I_H, I_L, I_C):
                rows[i][k] *= factor
    theta = 0.015
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


def local_compress(rows, i, w, ref_mult=16):
    seg = rows[i - w: i]
    hi = max(x[I_H] for x in seg)
    lo = min(x[I_L] for x in seg)
    mid = (hi + lo) / 2
    if mid == 0:
        return None
    ref0 = max(0, i - w * ref_mult)
    ref = rows[ref0:i]
    if len(ref) < w * 4:
        return None
    refs = []
    j = 0
    while j + w <= len(ref):
        s2 = ref[j: j + w]
        h2 = max(x[I_H] for x in s2)
        l2 = min(x[I_L] for x in s2)
        m2 = (h2 + l2) / 2
        if m2:
            refs.append((h2 - l2) / m2)
        j += max(1, w // 2)
    if not refs:
        return None
    ref_med = sorted(refs)[len(refs) // 2]
    return (hi - lo) / mid / ref_med if ref_med else None


def find_flats_v5(rows, window=16, compress_thresh=0.65, gap_allow=6,
                  p_low=0.10, p_high=0.90, close_break_n=3, band_max_pct=1.0,
                  stride=STRIDE):
    n = len(rows)
    is_flat = [False] * n
    for i in range(window, n, stride):
        c = local_compress(rows, i, window)
        if c is not None and c < compress_thresh:
            for j in range(i, min(i + stride, n)):
                is_flat[j] = True
    true_pos = [i for i in range(n) if is_flat[i]]
    flats = []
    if not true_pos:
        return flats
    segs = []
    s = true_pos[0]
    prev = s
    for p in true_pos[1:]:
        if p - prev > gap_allow:
            segs.append((s, prev))
            s = p
        prev = p
    segs.append((s, prev))
    for (a, b) in segs:
        if b - a < window:
            continue
        cs = sorted(rows[i][I_C] for i in range(a, b + 1))
        lo_b = cs[min(len(cs) - 1, int(len(cs) * p_low))]
        hi_b = cs[min(len(cs) - 1, int(len(cs) * p_high))]
        body_h = sorted(max(rows[i][I_O], rows[i][I_C]) for i in range(a, b + 1)
                        if lo_b <= rows[i][I_C] <= hi_b)
        body_l = sorted(min(rows[i][I_O], rows[i][I_C]) for i in range(a, b + 1)
                        if lo_b <= rows[i][I_C] <= hi_b)
        if not body_h or not body_l:
            continue
        n_b = len(body_h)
        band_h = body_h[min(n_b - 1, int(n_b * 0.90))]
        band_l = body_l[max(0, int(n_b * 0.10))]
        end = b
        streak = 0
        last_good = b
        for i in range(a, b + 1):
            c = rows[i][I_C]
            if c > band_h or c < band_l:
                streak += 1
                if streak >= close_break_n:
                    end = last_good
                    break
            else:
                streak = 0
                last_good = i
        if end - a + 1 < window:
            continue
        seg = rows[a: end + 1]
        closes = [x[I_C] for x in seg]
        nn = len(closes)
        xs = list(range(nn))
        mx = (nn - 1) / 2
        my = sum(closes) / nn
        sxy = sum((xs[i] - mx) * (closes[i] - my) for i in range(nn))
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sxy / sxx if sxx else 0
        resid = sum((closes[i] - (my + slope * (xs[i] - mx))) ** 2
                    for i in range(nn))
        se = (resid / (nn - 2)) ** 0.5 if nn > 2 else 0
        se_slope = se / sxx ** 0.5 if sxx else 0
        slope_t = abs(slope) / se_slope if se_slope else 0
        bwidth = max(band_h - band_l, 1e-9)
        touch_tol = 0.15 * bwidth
        eh_list = [max(rows[i][I_O], rows[i][I_C]) for i in range(a, end + 1)]
        el_list = [min(rows[i][I_O], rows[i][I_C]) for i in range(a, end + 1)]
        up_touch = dn_touch = 0
        for i in range(1, nn - 1):
            if eh_list[i] >= eh_list[i - 1] and eh_list[i] >= eh_list[i + 1]:
                if band_h - eh_list[i] <= touch_tol:
                    up_touch += 1
            if el_list[i] <= el_list[i - 1] and el_list[i] <= el_list[i + 1]:
                if el_list[i] - band_l <= touch_tol:
                    dn_touch += 1
        mid_c = sorted(closes)[nn // 2] if nn else 0
        band_pct = (band_h - band_l) / mid_c * 100 if mid_c else 99
        if band_pct >= band_max_pct:
            continue
        flats.append({"end": end, "hi": band_h, "lo": band_l,
                      "slope_t": slope_t, "up_touch": up_touch,
                      "dn_touch": dn_touch, "band_pct": band_pct})
    return flats


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ev2 = []
    ev3 = []
    daily = {}
    for sym, exch in SYMS.items():
        rows, tdays, tclose, bad, bad_pts = load_5m_adj(sym, exch)
        daily[sym] = (tdays, tclose)
        by_day = defaultdict(list)
        for r in rows:
            by_day[r[I_DAY]].append(r)
        print(f"[load] {sym}: 5m bars={len(rows)} 坏行 {bad} 复权护栏跳过 {bad_pts}")
        h60 = load_60m_raw(sym, exch)

        # ── 臂2：逐交易日节点 ──
        for td in tdays:
            day_bars = by_day.get(td) or []
            if not day_bars:
                continue
            node = day_bars[-1]
            node_dt = node[I_DT]
            tail = [b for b in rows if b[I_DT] <= node_dt][-1500:]
            if len(tail) < 500:
                continue
            h60n = [b for b in h60 if b[I_DT] <= node_dt][-300:]
            th = trend_h1_60m(h60n) if len(h60n) >= 60 else "震荡"
            r = pullback_arm(tail, CFG5)
            if r is None:
                continue
            if r["dir"] == "long" and th != "多头":
                continue
            if r["dir"] == "short" and th != "空头":
                continue
            ev2.append({"sym": sym, "td": td, "dir": r["dir"],
                        "score": r["score"], "entry": node[I_C]})

        # ── 臂3：全序列箱体 → is_current 段尾候选 ──
        flats = find_flats_v5(rows, window=FLAT["window"],
                              compress_thresh=FLAT["compress"],
                              gap_allow=FLAT["gap_allow"],
                              band_max_pct=FLAT["band_max"])
        for f in flats:
            e = f["end"]
            if e + 1 >= len(rows):
                continue
            brk = 0
            ok = True
            for j in range(e + 1, min(e + FLAT["tail_margin"] + 1, len(rows))):
                c = rows[j][I_C]
                if c > f["hi"] or c < f["lo"]:
                    brk += 1
                    if brk >= 2:
                        ok = False
                        break
                else:
                    brk = 0
            if not ok:
                continue
            node_bar = rows[min(e + FLAT["tail_margin"], len(rows) - 1)]
            c0 = node_bar[I_C]
            tol = 0.15 * (f["hi"] - f["lo"])
            d = "long" if c0 <= f["lo"] + tol else \
                "short" if c0 >= f["hi"] - tol else None
            if d is None:
                continue
            ev3.append({"sym": sym, "td": node_bar[I_DAY], "dir": d,
                        "entry": c0, "band_pct": f["band_pct"]})

    def fwd(sym, td, entry, d_dir):
        tdl, cl = daily[sym]
        if td not in cl:
            return {}
        i = tdl.index(td)
        out = {}
        for h in HORIZONS:
            j = i + h
            if j < len(tdl):
                out[h] = (cl[tdl[j]] / entry - 1) * d_dir
        return out

    for e in ev2:
        e["fwd"] = fwd(e["sym"], e["td"], e["entry"],
                       1 if e["dir"] == "long" else -1)
    for e in ev3:
        e["fwd"] = fwd(e["sym"], e["td"], e["entry"],
                       1 if e["dir"] == "long" else -1)

    def tbl(rows, label):
        L = [f"**{label}**", "",
             "| 口径 | " + " | ".join(f"+{k}日胜率" for k in HORIZONS) + " | "
             + " | ".join(f"+{k}日均值" for k in HORIZONS) + " |",
             "|---|" + "---|" * (len(HORIZONS) * 2)]
        for tag, cond in (("全样本", lambda e: True),
                          ("in <2022", lambda e: e["td"] < SPLIT),
                          ("out ≥2022", lambda e: e["td"] >= SPLIT)):
            sub = [e for e in rows if cond(e)]
            cells = []
            for h in HORIZONS:
                v = [e["fwd"][h] for e in sub if h in e["fwd"]]
                cells.append(f"{sum(1 for x in v if x > 0) / len(v):.1%}（n={len(v)}）"
                             if v else "-")
            for h in HORIZONS:
                v = [e["fwd"][h] for e in sub if h in e["fwd"]]
                cells.append(f"{sum(v) / len(v):+.2%}" if v else "-")
            L.append(f"| {tag} | " + " | ".join(cells) + " |")
        return L

    L = ["# RS020 合并选品对照回测（臂1 已测 / 臂2 臂3 本次 / 预注册判读）", "",
         "- 数据：5m 全历史后复权（工程 _detect_and_splice 同款+坏点护栏，2015 起）；",
         "- 臂2=Hermes pullback 全判据（zigzag θ0.8% 四因子+60m HH/HL θ1.5% 过滤，",
         "  5m 尾 1500 根窗，每交易日节点）；臂3=find_flats_v5 箱体+边缘触碰候选",
         "  （local_compress stride=4 近似）；",
         "- 前瞻=事件收盘→交易日 +5/+10/+20 收盘（方向调整，无成本）；",
         "- 臂1 对照（RS019 日线口径）：趋势+EMA20 贴近 +20日 43.8%/−0.54%",
         "  （OOS 44.6%/−0.64%）。", ""]

    L += ["## 臂2：Hermes pullback 四因子（生产参数）", ""]
    L += tbl(ev2, f"n={len(ev2)}")
    L += ["", "### 臂2 分方向", ""]
    for d in ("long", "short"):
        sub = [e for e in ev2 if e["dir"] == d]
        if sub:
            L += tbl(sub, d)
        L.append("")

    L += ["## 臂3：flats 箱体边缘触碰", ""]
    L += tbl(ev3, f"n={len(ev3)}")

    L += ["", "## 预注册判读（合并设计 v2 §7.3）", ""]
    res = {}
    for name, rows in (("臂2", ev2), ("臂3", ev3)):
        sub = [e for e in rows if e["td"] >= SPLIT and 20 in e["fwd"]]
        v = [e["fwd"][20] for e in sub]
        res[name] = (sum(v) / len(v) if v else None, len(v))
    verdict = []
    for name, (m, n) in res.items():
        if m is not None and m > 0 and m > -0.0054:
            verdict.append(f"{name} OOS +20日 {m:+.2%}（n={n}）达标")
    if verdict:
        L.append("- " + "；".join(verdict) + " → **合并方向成立**（臂4 hybrid 深化）")
    else:
        det = "；".join(f"{k} OOS {v[0]:+.2%}（n={v[1]}）" if v[0] is not None
                        else f"{k} n不足" for k, v in res.items())
        L.append(f"- {det} → **全臂 OOS 为负 → 选品层重构转向 RS001 三因子直接建模**")

    L += ["", "## 诚实声明", "",
          "- 5/10 品种子集；5m 后复权为研究侧移植（对生产 5m 未平滑=偏差修正，",
          "  生产 5m zigzag 存在换月幻影污染——MA2609→2701 −9.3% 案例在档）；",
          "- 臂2 60m 趋势过滤忠实 Hermes 4% 平滑 B 方案（与 DEC006 D-2 统一口径",
          "  并存，两者均消除大跳空）；流动性门槛未移植（AMT_MIN 在未拉取模块，",
          "  5 主连均为活跃品种，影响小）；",
          "- 臂3 local_compress 步长 4 近似（生产逐根）；收盘口径非执行口径。"]

    out = OUT / "merge_backtest.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    for name, rows in (("臂2", ev2), ("臂3", ev3)):
        sub = [e for e in rows if e["td"] >= SPLIT and 20 in e["fwd"]]
        v = [e["fwd"][20] for e in sub]
        if v:
            print(f"{name} OOS +20d: n={len(v)} win={sum(1 for x in v if x>0)/len(v):.1%} "
                  f"avg={sum(v)/len(v):+.2%}")


if __name__ == "__main__":
    main()
