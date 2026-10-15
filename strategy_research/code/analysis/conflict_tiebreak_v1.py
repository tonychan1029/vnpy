# RESEARCH ONLY - 未获用户批准不得正式运行
"""§9d 编排裁决规则 v1 时代复验（MTG004 登记册"v1 下待复验"项）。

在 conflict_tiebreak.py 同一配对逻辑上新增两层检验：
  1) 剔除已否决家族：MTG004 已否决 EMA20_PULLBACK（深跌接刀），而 §9d
     原证据的回调腿错误"多为 EMA20_PULLBACK 逆势腿"——剔除后规则是否仍成立；
  2) v1 regime 分层：冲突对按窗口起点的 v1 context_tag 分层
     （breakout/range/reversal/trend_*），检验"跟随突破"优势是否跨 regime 稳健。
配对口径不变：同品种、方向相反、bar_time 相差 ≤5h；裁决=窗口起点后 20 根
真实方向；±1R/笔名义。
输出：assets/MTG004/conflict_tiebreak_v1.md
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"
HORIZON = 20
WIN = timedelta(hours=5)

FAMILY = {
    "BREAKOUT_KEY_LEVEL": "突破", "H2L2_TREND": "突破",
    "FAKE_BREAKOUT_REVERSE": "突破",
    "STRUCTURE_PULLBACK": "回调", "EMA20_PULLBACK": "回调",
}
SYMS = {"RB": "SHFE", "CU": "SHFE", "AG": "SHFE",
        "M": "DCE", "MA": "CZCE", "TA": "CZCE"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    closes_map, tag_map = {}, {}
    for sym, exch in SYMS.items():
        dts, closes = [], []
        with (DATA / exch / sym / f"{sym}.csv").open(newline="",
                                                     encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(datetime.strptime(r["datetime"],
                                             "%Y-%m-%d %H:%M:%S"))
                closes.append(float(r["close"]))
        closes_map[sym] = (dts, closes)
        tags = {}
        with (TAGS / f"{sym}_context_tags.csv").open(
                newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                tags[r["datetime"]] = (r.get("context_tag") or "").strip().lower()
        tag_map[sym] = tags

    def fwd(sym, dt):
        dts, closes = closes_map[sym]
        if dt > dts[-1]:
            return None
        lo, hi = 0, len(dts) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if dts[mid] < dt:
                lo = mid + 1
            else:
                hi = mid
        i = lo
        if i + HORIZON >= len(closes):
            return None
        return closes[i + HORIZON] / closes[i] - 1

    ev = defaultdict(lambda: ([], []))
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            fam = FAMILY.get(r["signal_id"])
            if fam is None:
                continue
            try:
                dt = datetime.strptime(r["bar_time"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            lst, oth = ev[r["symbol"]]
            d = 1 if r["direction"] == "long" else -1
            if fam == "突破":
                lst.append((dt, d, r["signal_id"]))
            else:
                oth.append((dt, d, r["signal_id"]))

    def stratum(tag):
        if tag in (None, ""):
            return "无标签"
        if tag == "breakout":
            return "breakout"
        if tag == "range":
            return "range"
        if tag == "reversal":
            return "reversal"
        return "trend"

    # 桶：(层, 腿口径)；每对恰入 4 桶：层×腿、层×all、全样本×all、全样本×腿
    agg = defaultdict(lambda: [0, 0, 0])   # key -> [n, 突破对, 回调对]
    used = set()
    for sym, (b_events, p_events) in ev.items():
        tags = tag_map[sym]
        b_events.sort()
        p_events.sort()
        for bt, bd, bid in b_events:
            for pt, pd, pid in p_events:
                if abs((pt - bt).total_seconds()) > WIN.total_seconds():
                    continue
                if pd == bd:
                    continue
                key = (sym, bt, pt)
                if key in used:
                    continue
                used.add(key)
                fw = fwd(sym, min(bt, pt))
                if fw is None:
                    continue
                t0 = min(bt, pt)
                tag = tags.get(t0.strftime("%Y-%m-%d %H:%M:%S"), "")
                st = stratum(tag)
                b_ok = 1 if bd == (1 if fw > 0 else -1) else 0
                p_ok = 1 if pd == (1 if fw > 0 else -1) else 0
                ex = "EMA20_PULLBACK" in (bid, pid)
                for s_tag, s_ex in ((st, ex), (st, "all"),
                                    ("全样本", "all"), ("全样本", ex)):
                    a = agg[(s_tag, s_ex)]
                    a[0] += 1
                    a[1] += b_ok
                    a[2] += p_ok

    def row(name, key):
        n, bok, pok = agg[key]
        if not n:
            return f"| {name} | 0 | - | - | - |"
        return (f"| {name} | {n} | {bok / n:.1%} | {pok / n:.1%} | "
                f"{(2 * bok - n):+d}R |")

    L = ["# §9d 编排裁决规则 v1 时代复验（登记册\"v1 下待复验\"项）", "",
         "- 配对口径与 conflict_tiebreak.py 完全一致（±5h 同窗反向、20 根裁决）；",
         "- 新增：①剔除已否决 EMA20_PULLBACK 腿的变体；②按窗口起点 v1 context_tag 分层。",
         "", "## 1. 全样本与剔除变体", "",
         "| 口径 | 冲突对 | 突破正确率 | 回调正确率 | 跟随突破期望净R |",
         "|---|---|---|---|---|"]
    L.append(row("全样本（复现 §9d）", ("全样本", "all")))
    L.append(row("无 EMA20_PULLBACK 腿", ("全样本", False)))
    L.append(row("含 EMA20_PULLBACK 腿", ("全样本", True)))

    L += ["", "## 2. 按 v1 context_tag 分层（全口径，含 EMA20）", "",
          "| v1 regime | 冲突对 | 突破正确率 | 回调正确率 | 跟随突破期望净R |",
          "|---|---|---|---|---|"]
    for st in ("breakout", "range", "reversal", "trend", "无标签"):
        L.append(row(st, (st, "all")))

    L += ["", "## 3. 按 v1 regime 分层（剔除 EMA20_PULLBACK 腿）", "",
          "| v1 regime | 冲突对 | 突破正确率 | 回调正确率 | 跟随突破期望净R |",
          "|---|---|---|---|---|"]
    for st in ("breakout", "range", "reversal", "trend", "无标签"):
        L.append(row(st, (st, True)))

    L += ["", "判读：若剔除后突破正确率仍 >50% 且各 regime 方向一致，",
          "§9d 规则在存活家族上成立，登记册\"v1 下待复验\"闭环；",
          "终验=v2 标签基线重跑时复核（HO004 落地后 trend 标签分布将变）。"]

    out = OUT / "conflict_tiebreak_v1.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    main()
