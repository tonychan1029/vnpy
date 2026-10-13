# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS015 离线诊断：context_tag v2 候选定义实测（reversal 重定义 / range 判别力）。

目的（RS015 议题文档的实证底座）：
  - A2：v0/v1 reversal 规则（EMA 斜率×位置异号）抓的是趋势内回调而非已实现
    反转（v1 列精确率 15.7%、LR 0.82 反向信息）。本脚本实测一族"已实现结构
    破坏"候选规则（先行腿 + 反向位移 + 结构破位/回撤比例）对 GT REVERSAL
    （往返实现，v1.1 协议）的列精确率 / 似然比 / 触发占比 / 落点分布。
  - A1：v1 宽口径 range 列似然比仅 1.09（近无信息）。实测引入"波动率状态
    变量"（过去 20 根净位移镜像、Kaufman ER20、内带位置）的候选组合。

方法纪律：
  - 与 RS012 同一扫描网格（GT CSV 逐点内连接，STEP=4/horizon=20/ATR14，
    UNDEFINED 已在真值侧剔除），全部指标可与 v0/v1 验收数字直接对比。
  - 基线锚=工程 v1 tags CSV（context_tags/）原样内连接，验证对齐无误。
  - in/out 切分 2022-01-01（与 rs012_run 一致）；候选固定为下列清单，
    不因结果增删臂；按 in 样本判读、out 确认，防多重比较。

输出：assets/RS015/context_v2_diagnostic.md
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # strategy_research/code
GT_DIR = ROOT.parent / "assets" / "RS012"
OUT = ROOT.parent / "assets" / "RS015"
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")

SYMBOLS = {"RB": "SHFE", "CU": "SHFE", "AG": "SHFE",
           "M": "DCE", "MA": "CZCE", "TA": "CZCE"}
SPLIT = "2022-01-01"

LEG_K = 2.0        # 先行腿幅度（对齐 GT TREND 2xATR 量级）
CTRP_K = 1.0       # 反向位移幅度（沿用 v1 已实现位移量级）
RETR_K = 0.5       # 回撤比例（GT 往返条件的可实现代理）
ER_K = 0.30        # ER20 低效率阈值
NET_K = 1.0        # 过去 20 根净位移（GT RANGE 未来净位移 <1xATR 的镜像）
BAND_K = 0.15      # 内带（距 40 根区间边缘 15% 宽度以上）


def load_bars(path: Path):
    dts, highs, lows, closes = [], [], [], []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dts.append(r["datetime"])
            highs.append(float(r["high"]))
            lows.append(float(r["low"]))
            closes.append(float(r["close"]))
    return dts, highs, lows, closes


def atr_series(highs, lows, closes, n=14):
    out = [None] * len(closes)
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
        if len(trs) >= n:
            out[i] = sum(trs[-n:]) / n
    return out


def ema_series(closes, period=20):
    out = [None] * len(closes)
    if len(closes) < period:
        return out
    e = sum(closes[:period]) / period
    out[period - 1] = e
    k = 2.0 / (period + 1)
    for i in range(period, len(closes)):
        e = e + k * (closes[i] - e)
        out[i] = e
    return out


def fractal_pivots(highs, lows):
    """2 根分形摆动点（M-PT-001 口径）：返回 (pivL, pivH) 索引列表。"""
    n = len(lows)
    pivL = [i for i in range(2, n - 2)
            if all(lows[i] < lows[j] for j in range(i - 2, i + 3) if j != i)]
    pivH = [i for i in range(2, n - 2)
            if all(highs[i] > highs[j] for j in range(i - 2, i + 3) if j != i)]
    return pivL, pivH


class Feats:
    """单个 as_of 的全部候选特征（只含 as_of 及之前数据）。"""
    __slots__ = ("slope", "diff", "atr", "width", "net20", "er20", "inner",
                 "exc5", "leg_rev", "c_ret", "s_break", "f_half")

    def __init__(self) -> None:
        self.leg_rev = False
        self.c_ret = False
        self.s_break = False
        self.f_half = False


def build_feats(i, closes, highs, lows, emas, atr, pivL, pivH) -> Feats:
    f = Feats()
    c = closes[i]
    ema = emas[i]
    f.atr = atr
    f.diff = c - ema
    f.slope = ema - emas[i - 5]
    pre = closes[i - 40: i]
    hi40, lo40 = max(pre), min(pre)
    f.width = hi40 - lo40
    f.net20 = abs(c - closes[i - 20])
    path = sum(abs(closes[j] - closes[j - 1]) for j in range(i - 19, i + 1))
    f.er20 = f.net20 / path if path > 0 else 1.0
    f.inner = lo40 + BAND_K * f.width <= c <= hi40 - BAND_K * f.width

    win = closes[i - 4: i + 1]
    if f.slope > 0:
        f.exc5 = max(win) - win[-1]
    else:
        f.exc5 = win[-1] - min(win)

    # ── 已实现结构破坏特征（双向对称）──────────────────────────
    # 下行反转（先升后跌）：近 20 根最高 close 为腿端，腿基=其前 40 根窗内最低
    seg = closes[i - 19: i + 1]
    tH = max(range(len(seg)), key=lambda j: seg[j])
    H20 = seg[tH]
    base_up = min(closes[max(0, i - 40): i - 19 + tH + 1])
    leg_up = H20 - base_up
    # 上行反转（先跌后涨）：镜像
    tL = min(range(len(seg)), key=lambda j: seg[j])
    L20 = seg[tL]
    base_dn = max(closes[max(0, i - 40): i - 19 + tL + 1])
    leg_dn = base_dn - L20

    f.leg_rev = leg_up >= LEG_K * atr or leg_dn >= LEG_K * atr
    ret_up = H20 - c                       # 自高点回落
    ret_dn = c - L20                       # 自低点回升
    f.c_ret = ret_up >= CTRP_K * atr or ret_dn >= CTRP_K * atr

    s_dn = s_up = False
    for p in reversed(pivL):               # 最近的可确认摆动低点
        if p <= i - 2 and i - p <= 40:
            s_dn = c < lows[p]
            break
    for p in reversed(pivH):               # 最近的可确认摆动高点
        if p <= i - 2 and i - p <= 40:
            s_up = c > highs[p]
            break
    f.s_break = s_dn or s_up

    fh = False
    if leg_up >= LEG_K * atr and leg_up > 0:
        fh = fh or ret_up / leg_up >= RETR_K
    if leg_dn >= LEG_K * atr and leg_dn > 0:
        fh = fh or ret_dn / leg_dn >= RETR_K
    f.f_half = fh
    return f


def rev_v0(f: Feats) -> bool:      # v0：斜率×位置异号（基线）
    return f.slope * f.diff < 0


def rev_v1(f: Feats) -> bool:      # v1 现行：v0 + 最近 5 根 ≥1ATR 反向位移
    return f.slope * f.diff < 0 and f.exc5 >= 1.0 * f.atr


def rev_A(f: Feats) -> bool:       # R-A：先行腿 + 1ATR 已实现反向位移
    return f.leg_rev and f.c_ret


def rev_B(f: Feats) -> bool:       # R-B：A + 结构破位（摆动点穿越）
    return f.leg_rev and f.c_ret and f.s_break


def rev_C(f: Feats) -> bool:       # R-C：A + 回撤≥50%（GT 往返代理）
    return f.leg_rev and f.c_ret and f.f_half


def rev_D(f: Feats) -> bool:       # R-D：A + (结构破位 或 回撤≥50%)
    return f.leg_rev and f.c_ret and (f.s_break or f.f_half)


def rng_v1(f: Feats) -> bool:      # v1 宽口径（现行）
    return abs(f.diff) <= 0.5 * f.atr and f.width <= 6 * f.atr


def rng_net(f: Feats) -> bool:     # NR1：过去 20 根净位移镜像
    return f.net20 < NET_K * f.atr


def rng_er(f: Feats) -> bool:      # NR2：ER20 低方向效率
    return f.er20 <= ER_K


def rng_net_er(f: Feats) -> bool:  # NR3：净位移 ∧ ER
    return f.net20 < NET_K * f.atr and f.er20 <= ER_K


def rng_full(f: Feats) -> bool:    # NR4：净位移 ∧ ER ∧ 内带
    return f.net20 < NET_K * f.atr and f.er20 <= ER_K and f.inner


REV_RULES = (("V0 斜率×位置(基线)", rev_v0, "repl"),
             ("V1 +5根反向位移(现行)", rev_v1, "repl"),
             ("R-A 先行腿+1ATR反向位移", rev_A, "repl"),
             ("R-A 先行腿+1ATR反向位移", rev_A, "hi"),
             ("R-B A+结构破位", rev_B, "repl"),
             ("R-B A+结构破位", rev_B, "hi"),
             ("R-C A+回撤50%", rev_C, "repl"),
             ("R-C A+回撤50%", rev_C, "hi"),
             ("R-D A+(破位或回撤50%)", rev_D, "repl"),
             ("R-D A+(破位或回撤50%)", rev_D, "hi"))
RNG_RULES = (("V1 宽口径(现行)", rng_v1),
             ("NR1 net20<1ATR(镜像)", rng_net),
             ("NR2 ER20≤0.30", rng_er),
             ("NR3 net∧ER", rng_net_er),
             ("NR4 net∧ER∧内带", rng_full))


def chain_pred(f: Feats, bo: bool, rng_rule, rev_rule, rev_hi: bool) -> str:
    """v1 优先级链，range/reversal 分支可替换；rev_hi=把 reversal 提到 trend 之前。"""
    if bo:
        return "BREAKOUT"
    if rng_rule(f):
        return "RANGE"
    if rev_hi and rev_rule(f):
        return "REVERSAL"
    if f.slope * f.diff > 0:
        return "TREND_STRONG" if abs(f.slope) >= 0.25 * f.atr else "TREND_CH"
    if rev_rule(f):
        return "REVERSAL"
    return "TREND_CH"


def adapt(tag: str, f: Feats) -> str:
    """tag_adapter 映射：trend 拆向按 diff 符号（忠实 v0/v1 规则）。"""
    if tag == "TREND_STRONG" or tag == "TREND_CH":
        return "TREND_UP" if f.diff > 0 else "TREND_DN"
    return tag


def evaluate(rows, target: str):
    """rows: [(sym, dt, gt, pred)]；返回候选指标 dict。"""
    n = len(rows)
    fires = [(g, s, d) for s, d, g, p in rows if p == target]
    fire_n = len(fires)
    hit = sum(1 for g, _, _ in fires if g == target)
    prec = hit / fire_n if fire_n else 0.0
    base = sum(1 for _, _, g, _ in rows if g == target) / n if n else 0.0
    landing = Counter(g for g, _, _ in fires)
    rec = hit / max(1, sum(1 for _, _, g, _ in rows if g == target))
    # target 行 top-pred（该 GT 类上引擎最常用标签的占比）
    trow = Counter(p for _, _, g, p in rows if g == target)
    top = max(trow.values()) / max(1, sum(trow.values())) if trow else 0.0
    # in/out 精确率
    io = {}
    for name, cond in (("in", lambda d: d < SPLIT), ("out", lambda d: d >= SPLIT)):
        sub = [(g, p) for _, d, g, p in rows if cond(d)]
        nf = sum(1 for g, p in sub if p == target)
        nh = sum(1 for g, p in sub if p == target and g == target)
        io[name] = (nh / nf if nf else None, nf)
    # 分品种精确率
    per = {}
    by_sym = defaultdict(list)
    for s, d, g, p in rows:
        by_sym[s].append((g, p))
    for s, sub in by_sym.items():
        nf = sum(1 for g, p in sub if p == target)
        nh = sum(1 for g, p in sub if p == target and g == target)
        per[s] = nh / nf if nf else None
    return {"n": n, "fires": fire_n, "share": fire_n / n if n else 0,
            "prec": prec, "base": base, "lr": prec / base if base else 0,
            "recall": rec, "top": top, "landing": landing, "io": io,
            "per": per}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = {}
    for sym, exch in SYMBOLS.items():
        dpath = DATA / exch / sym / f"{sym}.csv"
        dts, highs, lows, closes = load_bars(dpath)
        atrs = atr_series(highs, lows, closes)
        emas = ema_series(closes)
        pivL, pivH = fractal_pivots(highs, lows)
        idx = {d: i for i, d in enumerate(dts)}
        # breakout 迟滞态（复刻 ContextTaggerV1：enter 2 / exit 5）
        bo = [False] * len(closes)
        streak = nb = 0
        in_bo = False
        for i in range(40, len(closes)):
            a = atrs[i]
            if a is None or a <= 0:
                bo[i] = in_bo
                continue
            pre = closes[i - 40: i]
            hi40, lo40 = max(pre), min(pre)
            raw = closes[i] > hi40 + 0.1 * a or closes[i] < lo40 - 0.1 * a
            if raw:
                streak += 1
                nb = 0
                if streak >= 2:
                    in_bo = True
            else:
                nb += 1
                streak = 0
                if nb >= 5:
                    in_bo = False
            bo[i] = in_bo
        # GT 网格 + v1 tags 锚
        gt = {}
        gp = GT_DIR / f"{sym}_gt_labels.csv"
        if gp.exists():
            with gp.open(newline="", encoding="utf-8") as f:
                gt = {r["datetime"]: r["gt_label"] for r in csv.DictReader(f)}
        tags = {}
        tp = TAGS / f"{sym}_context_tags.csv"
        if tp.exists():
            with tp.open(newline="", encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    tags[r["datetime"]] = (r.get("context_tag") or "").strip().lower()
        feats = {}
        grid = []
        for d, g in gt.items():
            i = idx.get(d)
            if i is None or i < 45 or atrs[i] in (None, 0) or emas[i] is None:
                continue
            feats[i] = build_feats(i, closes, highs, lows, emas, atrs[i], pivL, pivH)
            grid.append((i, d, g))
        cache[sym] = {"grid": grid, "feats": feats, "bo": bo, "tags": tags,
                      "n_bars": len(closes)}
        print(f"[ok] {sym}: bars={len(closes)} grid={len(grid)} v1tags={len(tags)}")

    rows_v1 = []      # 工程交付 tags 锚（对齐验证）
    rows_rng = {name: [] for name, _ in RNG_RULES}
    rows_rev = {(name, plc): [] for name, _, plc in REV_RULES}
    for sym, c in cache.items():
        for i, d, g in c["grid"]:
            f = c["feats"][i]
            t = c["tags"].get(d)
            if t:
                pred = {"breakout": "BREAKOUT", "range": "RANGE",
                        "reversal": "REVERSAL"}.get(t)
                if pred is None:
                    pred = "TREND_UP" if f.diff > 0 else "TREND_DN"
                rows_v1.append((sym, d, g, pred))
            for name, rule in RNG_RULES:
                p = adapt(chain_pred(f, c["bo"][i], rule, rev_v1, False), f)
                rows_rng[name].append((sym, d, g, p))
            for name, rule, plc in REV_RULES:
                hi = plc == "hi"
                p = adapt(chain_pred(f, c["bo"][i], rng_v1, rule, hi), f)
                rows_rev[(name, plc)].append((sym, d, g, p))

    L = ["# RS015 离线诊断：context_tag v2 候选定义实测", "",
         "- 网格：GT v1.1（STEP=4 / horizon=20 / ATR14，UNDEFINED 剔除）逐点内连接，",
         "  与 RS012 §5 / v1_acceptance 完全同口径，指标可直接对比。",
         "- 基线锚=工程交付 v1 tags CSV 原样连接；候选=研究侧复刻链（breakout 迟滞",
         "  enter2/exit5、range/trend/reversal 分支同位替换）。",
         "- in/out 切分 2022-01-01；候选清单预注册于脚本头，未因结果增删。", ""]
    total_grid = sum(len(c["grid"]) for c in cache.values())
    L.append(f"合并网格 n={total_grid}")

    # ── 0. 对齐验证 ──
    r = evaluate(rows_v1, "RANGE")
    r2 = evaluate(rows_v1, "REVERSAL")
    r3 = evaluate(rows_v1, "BREAKOUT")
    L += ["", "## 0. 对齐验证（v1 tags 锚 vs 官方验收数字）", "",
          "| 列 | 本次实测精确率 | 官方 v1_acceptance |",
          "|---|---|---|",
          f"| RANGE 列 | {r['prec']:.1%}（LR {r['lr']:.2f}） | 19.0%（LR 1.09） |",
          f"| REVERSAL 列 | {r2['prec']:.1%}（LR {r2['lr']:.2f}） | 15.7%（LR 0.82） |",
          f"| BREAKOUT 列 | {r3['prec']:.1%}（LR {r3['lr']:.2f}） | 31.8%（LR 1.15；v1_acceptance 原载 38.0%/3.8× 系行列读位笔误，勘误见 RS015 §2.3） |",
          f"| RANGE top-pred | {r['top']:.1%} | 31.1% |", ""]

    # ── 1. reversal 候选 ──
    L += ["## 1. A2 reversal 候选（GT REVERSAL 基率见各行 base）", "",
          "| 候选 | 位置 | 触发 | 占比 | 列精确率 | LR | 召回 | top-pred | in 精确率 | out 精确率 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    rev_detail = {}
    for (name, plc), rows in rows_rev.items():
        r = evaluate(rows, "REVERSAL")
        rev_detail[(name, plc)] = r
        io = r["io"]
        fins = f"{io['in'][0]:.1%}({io['in'][1]})" if io["in"][0] is not None else "-"
        fouts = f"{io['out'][0]:.1%}({io['out'][1]})" if io["out"][0] is not None else "-"
        L.append(f"| {name} | {plc} | {r['fires']} | {r['share']:.1%} | "
                 f"**{r['prec']:.1%}** | {r['lr']:.2f} | {r['recall']:.1%} | "
                 f"{r['top']:.1%} | {fins} | {fouts} |")
    L += ["", "GT REVERSAL 基率："
          f"{rev_detail[('V1 +5根反向位移(现行)', 'repl')]['base']:.1%}", ""]

    # 落点分布（最优三候选 + v1 现行）
    L += ["### 落点分布（fire → GT 类占比，前 3）", "",
          "| 候选 | 位置 | 落点 top3 |", "|---|---|---|"]
    for key in (("V1 +5根反向位移(现行)", "repl"), ("R-A 先行腿+1ATR反向位移", "repl"),
                ("R-B A+结构破位", "repl"), ("R-D A+(破位或回撤50%)", "repl"),
                ("R-D A+(破位或回撤50%)", "hi")):
        r = rev_detail.get(key)
        if not r or not r["fires"]:
            continue
        tot = r["fires"]
        top3 = ", ".join(f"{k} {v / tot:.0%}" for k, v in r["landing"].most_common(3))
        L.append(f"| {key[0]} | {key[1]} | {top3} |")

    L += ["", "### 分品种精确率（reversal 候选）", "",
          "| 候选 | 位置 | RB | CU | AG | M | MA | TA |", "|---|---|---|---|---|---|---|---|"]
    for (name, plc), r in rev_detail.items():
        if not r["fires"]:
            continue
        cells = " | ".join(f"{r['per'][s]:.0%}" if r["per"][s] is not None else "-"
                           for s in SYMBOLS)
        L.append(f"| {name} | {plc} | {cells} |")

    # ── 2. range 候选 ──
    L += ["", "## 2. A1 range 候选（波动率状态变量）", "",
          "| 候选 | 触发 | 占比 | 列精确率 | LR | top-pred | in 精确率 | out 精确率 |",
          "|---|---|---|---|---|---|---|---|"]
    rng_detail = {}
    for name, rows in rows_rng.items():
        r = evaluate(rows, "RANGE")
        rng_detail[name] = r
        io = r["io"]
        fins = f"{io['in'][0]:.1%}({io['in'][1]})" if io["in"][0] is not None else "-"
        fouts = f"{io['out'][0]:.1%}({io['out'][1]})" if io["out"][0] is not None else "-"
        L.append(f"| {name} | {r['fires']} | {r['share']:.1%} | "
                 f"**{r['prec']:.1%}** | {r['lr']:.2f} | {r['top']:.1%} | "
                 f"{fins} | {fouts} |")
    L += ["", f"GT RANGE 基率：{rng_detail['V1 宽口径(现行)']['base']:.1%}", ""]

    L += ["### 分品种精确率（range 候选）", "",
          "| 候选 | RB | CU | AG | M | MA | TA |", "|---|---|---|---|---|---|---|"]
    for name, r in rng_detail.items():
        cells = " | ".join(f"{r['per'][s]:.0%}" if r["per"][s] is not None else "-"
                           for s in SYMBOLS)
        L.append(f"| {name} | {cells} |")

    L += ["", "---", "",
          "*诊断脚本：`code/analysis/context_v2_diagnostic.py`（RESEARCH ONLY）；",
          "本文件为机器输出+人工判读底稿，结论与 v2 提案见 `20_research/RS015_*.md`。*"]
    out = OUT / "context_v2_diagnostic.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    main()
