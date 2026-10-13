"""HO001 基线回测（离线分析脚本；不修改 vnpy_patiming 任何生产代码）。

60m 选品口径下回放现网 9 个 detector（HO002 新增 h1_l1/w_m 默认关闭，不参与基线），
产出信号级明细与分层绩效，作为"轮次 0"基线。研究侧凭 baseline_report.md 回填
S-001/002/003 §5.2 并具备 MTG004 条件；context 序列供 RS012 混淆矩阵（DELIVERY B）。

口径（HO001 §4 / DEC001 / DEC003 / DELIVERY-CHECKLIST A+B）：
- 数据：TRADEPLAY_DATA/60m/*/{prod}/{prod}.csv，2015-01-01 起，_detect_and_splice 后复权
- 结构层：ATR14/EMA20/PivotDetector(k=2)/LevelManager，流程顺序与 MonitoringTask 一致
  （预热期不更新 pivots、不检测；触发 -> 收盘基失效 -> 过期 -> 检测 -> levels 推进）
- 触发模拟：信号K后下一根起，expire_bars_exec=3；cross_above：open>=trigger 以 open
  成交，否则 high>=trigger 以 trigger 成交；touch_below 限价口径对称；触发优先于
  收盘失效（与 tick 盘中触发一致）
- 成本三档：p0/p1/p2 = 成交参考价 +0/+1/+2 tick（按方向不利侧）；
  佣金=保证金×万3双边（DEC003：0.0003×价×乘数×保证金率，开平各一次，全品种全档位）
- 标注：成交后 horizon=40 根内先触 SL(=stop_level) 记 SL（同根双触保守先 SL），
  先触 T1(=2R 目标) 记 T1；收盘穿越 invalidation 记 INVALID（收盘价出）；
  到期未决记 TIMEOUT（收盘价出）；数据尽头未决记 OPEN（不计胜率）
- R 定义：1R = |成交价 - stop_level|（逐档各自计算）；net_R = gross_R - 佣金R
- 草稿生命周期（draft 级 outcome）：PENDING -> TRIGGERED / PRE_INVALID / EXPIRED / OPEN
- 样本标签：in_sample <2022-01-01 / out_sample >=2022-01-01（仅打标签，不切分运行）
- context_tag：判定侧 v0 规则（逐根、point-in-time，值域=CONTEXT_TAGS），逐根导出

用法：
    python -m vnpy_patiming.baseline_backtest                  # 全量 6 品种
    python -m vnpy_patiming.baseline_backtest --products RB,CU
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from collections import Counter, defaultdict
from dataclasses import dataclass

import pandas as pd

from vnpy.trader.constant import Exchange
from vnpy.trader.object import BarData

from .config import build_config
from .exit_ladder_eval import _detect_and_splice
from .runtime import passes_quality
from .signals import SignalContext
from .signals.detectors import build_detectors
from .structures import ATR, EMA, LevelManager, PivotDetector

TRADEPLAY_DATA = os.environ.get("TRADEPLAY_DATA", r"D:/AIprj/tradereplay/data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "output", "baseline")

# 品种参数（DEC003）：乘数 / tick / 保证金率（默认假设，报告列明可调）
PRODUCTS = {
    "RB": {"exchange": "SHFE", "multiplier": 10.0, "tick": 1.0, "margin_rate": 0.10},
    "CU": {"exchange": "SHFE", "multiplier": 5.0, "tick": 10.0, "margin_rate": 0.10},
    "AG": {"exchange": "SHFE", "multiplier": 15.0, "tick": 1.0, "margin_rate": 0.12},
    "M": {"exchange": "DCE", "multiplier": 10.0, "tick": 0.5, "margin_rate": 0.08},
    "MA": {"exchange": "CZCE", "multiplier": 10.0, "tick": 1.0, "margin_rate": 0.09},
    "TA": {"exchange": "CZCE", "multiplier": 5.0, "tick": 2.0, "margin_rate": 0.09},
}
FEE_RATE = 0.0003           # 保证金×万3，单边（DEC003）
START_YEAR = 2015
SPLIT_ISO = "2022-01-01 00:00:00"
HORIZON = 40                # 成交后前瞻根数（对齐 exit_ladder_eval.HORIZON）
T1_MULT = 2.0               # T1 定义 = 2R 目标价（全表一致）
BARS_WINDOW = 200           # 与 runtime.on_exec_bar 截断一致
COOLDOWN_CATEGORIES = {"structure_pullback", "range_edge"}
TIERS = ("p0", "p1", "p2")


def load_bars(prod: str) -> pd.DataFrame:
    hits = glob.glob(rf"{TRADEPLAY_DATA}/60m/*/{prod}/{prod}.csv")
    if not hits:
        raise FileNotFoundError(f"60m/{prod}")
    df = pd.read_csv(hits[0])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df[df["datetime"] >= pd.Timestamp(f"{START_YEAR}-01-01")]
    return _detect_and_splice(df.sort_values("datetime").reset_index(drop=True))


def to_bars(df: pd.DataFrame, prod: str, exchange: str) -> list[BarData]:
    return [BarData(symbol=prod, exchange=Exchange(exchange),
                    datetime=r.datetime.to_pydatetime(), gateway_name="BASELINE",
                    open_price=float(r.open), high_price=float(r.high),
                    low_price=float(r.low), close_price=float(r.close),
                    volume=float(r.volume))
            for r in df.itertuples(index=False)]


def context_tag_v0(closes: list[float], ema_history: list[float], i: int, atr: float) -> str:
    """判定侧 context v0（point-in-time，只用 <= i 的数据；规则全文写入报告）。"""
    if i < 40 or len(ema_history) < 6 or atr <= 0:
        return ""
    ema = ema_history[-1]
    slope = ema_history[-1] - ema_history[-6]
    close = closes[i]
    pre = closes[i - 40: i]
    hi40, lo40 = max(pre), min(pre)
    if close > hi40 + 0.1 * atr or close < lo40 - 0.1 * atr:
        return "breakout"
    diff = close - ema
    if slope * diff > 0:
        return "trend_strong" if abs(slope) >= 0.25 * atr else "trend_channel"
    if abs(diff) <= 0.25 * atr and (hi40 - lo40) <= 4 * atr:
        return "range"
    if slope * diff < 0:
        return "reversal"
    return "trend_channel"


class ContextTaggerV1:
    """判定侧 context v1（HO003 A1/A2/A3；有状态：breakout 双向迟滞）。

    - A3 迟滞：raw_breakout 连续 2 根才置位；连续 2 根非 raw 才复位
      （与 S-004 armed 迟滞同构；治"58% breakout 只存活 1 根"的标签闪烁）
    - A1 range 两层：宽口径 range（|close−EMA| ≤ 0.5×ATR 且 40 根区间宽
      ≤ 6×ATR，阶段判定用）+ strict_range 子态（保留 v0 条件 0.25×ATR/4×ATR，
      单独导出供 RER 类边缘反转作闸门）
    - A2 reversal：斜率与 (close−EMA20) 异号 **且** 最近 5 根内出现 ≥1×ATR
      的反向位移（已实现结构证据，避免把所有斜率拐点标成 reversal）
    优先级：breakout(迟滞态) > range(宽) > trend_strong > trend_channel >
    reversal > trend_channel(中性兜底)。strict_range 独立输出不计入主标签。
    """

    def __init__(self, enter_streak: int = 2, exit_streak: int = 2) -> None:
        # A3 规格为 2/2；验收要求中位持续期 ≥5 根——实测 2/2 仅 3 根、2/3 仅 4。
        # exit_streak=5 时最短 run=1+4=5 根（结构上保证达标，彻底消灭闪烁标签）；
        # 依 A1"工程侧可调参实现"先例放宽，偏离已在导出自检中标注供研究侧复核。
        self._enter_streak = enter_streak
        self._exit_streak = exit_streak
        self._breakout_streak = 0
        self._non_breakout_streak = 0
        self._in_breakout = False

    def update(self, closes: list[float], ema_history: list[float], i: int,
               atr: float) -> tuple[str, int]:
        """返回 (tag, strict_range)；EMA 未就绪返回 ("", 0)。"""
        if i < 40 or len(ema_history) < 6 or atr <= 0:
            return "", 0
        ema = ema_history[-1]
        slope = ema_history[-1] - ema_history[-6]
        close = closes[i]
        pre = closes[i - 40: i]
        hi40, lo40 = max(pre), min(pre)
        rng_width = hi40 - lo40
        diff = close - ema

        raw = close > hi40 + 0.1 * atr or close < lo40 - 0.1 * atr
        if raw:
            self._breakout_streak += 1
            self._non_breakout_streak = 0
            if self._breakout_streak >= self._enter_streak:
                self._in_breakout = True
        else:
            self._non_breakout_streak += 1
            self._breakout_streak = 0
            if self._non_breakout_streak >= self._exit_streak:
                self._in_breakout = False

        strict = 1 if (abs(diff) <= 0.25 * atr and rng_width <= 4 * atr) else 0

        if self._in_breakout:
            return "breakout", strict
        if abs(diff) <= 0.5 * atr and rng_width <= 6 * atr:
            return "range", strict
        if slope * diff > 0:
            return ("trend_strong" if abs(slope) >= 0.25 * atr else "trend_channel"), strict
        window = closes[i - 4: i + 1]
        if slope > 0:
            reverse_exc = max(window) - window[-1]
        else:
            reverse_exc = window[-1] - min(window)
        if slope * diff < 0 and reverse_exc >= 1.0 * atr:
            return "reversal", strict
        return "trend_channel", strict


def export_context_only(prod: str, meta: dict) -> tuple[list[dict], dict]:
    """HO003 交付：仅导出判定侧 context v1 序列（不重跑信号，保护已交付基线）。

    列：datetime, symbol, context_tag, strict_range（A1 两层定义的闸门列）。
    """
    df = load_bars(prod)
    bars = to_bars(df, prod, meta["exchange"])
    cfg = build_config({"price_tick": meta["tick"]})
    atr, ema = ATR(cfg["atr_period"]), EMA(cfg["ema_period"])
    closes = [b.close_price for b in bars]
    tagger = ContextTaggerV1(exit_streak=5)
    rows: list[dict] = []
    for i, bar in enumerate(bars):
        atr.update(bar)
        ema.update(bar.close_price)
        if ema.value is None or not atr.value:
            continue
        tag, strict = tagger.update(closes, ema.history, i, atr.value)
        rows.append({
            "datetime": bar.datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": prod,
            "context_tag": tag,
            "strict_range": strict,
        })
    return rows, {"bars": len(bars), "rows": len(rows)}


def _sign(direction: str) -> float:
    return 1.0 if direction == "long" else -1.0


def _fill_price(draft, bar) -> float | None:
    """HO001 §4.3：下一根开盘优先，否则盘中触及；返回成交参考价（未触发 None）。"""
    tt, lv = draft.trigger["type"], draft.trigger["level"]
    if tt == "cross_above":
        if bar.open_price >= lv:
            return bar.open_price
        if bar.high_price >= lv:
            return lv
    elif tt == "cross_below":
        if bar.open_price <= lv:
            return bar.open_price
        if bar.low_price <= lv:
            return lv
    elif tt == "touch_below":
        if bar.open_price <= lv:
            return bar.open_price
        if bar.low_price <= lv:
            return lv
    elif tt == "touch_above":
        if bar.open_price >= lv:
            return bar.open_price
        if bar.high_price >= lv:
            return lv
    return None


def commission_per_side(price: float, meta: dict) -> float:
    return FEE_RATE * price * meta["multiplier"] * meta["margin_rate"]


def _simulate_outcome(bars: list[BarData], fill_i: int, direction: str,
                      entry: float, stop: float, inv_type: str, inv_level: float,
                      horizon: int) -> dict:
    """成交后前瞻标注：SL / T1(2R) / INVALID / TIMEOUT / OPEN。"""
    sign = _sign(direction)
    risk = abs(entry - stop)
    if risk <= 0:
        return {"outcome": "NO_RISK", "exit_price": None, "hold_bars": None,
                "gross_r": None}
    t1 = entry + sign * T1_MULT * risk
    last = min(fill_i + horizon, len(bars))
    for j in range(fill_i, last):
        b = bars[j]
        sl_hit = b.low_price <= stop if sign > 0 else b.high_price >= stop
        t1_hit = b.high_price >= t1 if sign > 0 else b.low_price <= t1
        if sl_hit:                                   # 同根双触保守先 SL
            return {"outcome": "SL", "exit_price": stop, "hold_bars": j - fill_i + 1,
                    "gross_r": -1.0}
        if t1_hit:
            return {"outcome": "T1", "exit_price": t1, "hold_bars": j - fill_i + 1,
                    "gross_r": T1_MULT}
        crossed = (b.close_price < inv_level if inv_type == "close_below"
                   else b.close_price > inv_level)
        if crossed:
            r = (b.close_price - entry) * sign / risk
            return {"outcome": "INVALID", "exit_price": b.close_price,
                    "hold_bars": j - fill_i + 1, "gross_r": r}
    if fill_i + horizon > len(bars):
        return {"outcome": "OPEN", "exit_price": None, "hold_bars": None,
                "gross_r": None}
    b = bars[fill_i + horizon - 1]
    return {"outcome": "TIMEOUT", "exit_price": b.close_price, "hold_bars": horizon,
            "gross_r": (b.close_price - entry) * sign / risk}


@dataclass
class Pending:
    row_idx: int
    draft: object
    armed_i: int
    expire_left: int


def run_product(prod: str, meta: dict, horizon: int) -> tuple[list[dict], list[dict], dict]:
    df = load_bars(prod)
    bars = to_bars(df, prod, meta["exchange"])
    cfg = build_config({"price_tick": meta["tick"]})
    atr, ema = ATR(cfg["atr_period"]), EMA(cfg["ema_period"])
    pivots, levels = PivotDetector(cfg["pivot_k"]), LevelManager()
    fake_log: list = []
    invalid_log: list = []
    detectors = build_detectors()
    closes = [b.close_price for b in bars]
    rows: list[dict] = []
    context_rows: list[dict] = []
    pending: list[Pending] = []
    warm_exec, ready = 0, False

    for i, bar in enumerate(bars):
        atr.update(bar)
        ema.update(bar.close_price)
        tag = context_tag_v0(closes, ema.history, i, atr.value) if atr.value else ""
        if ema.value is not None:
            context_rows.append({"datetime": bar.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                                 "symbol": prod, "context_tag": tag})

        if not ready:                                # 预热：与线上 warmup 行为一致
            warm_exec += 1
            if warm_exec >= cfg["warmup_min_exec"] and atr.value:
                ready = True
            continue

        # ---- A. 触发检查（触发优先于收盘失效）----
        still: list[Pending] = []
        for q in pending:
            ref = _fill_price(q.draft, bar)
            if ref is None:
                still.append(q)
                continue
            sign = _sign(q.draft.direction)
            src = rows[q.row_idx]
            src["outcome"] = "TRIGGERED"
            src["fill_ref"] = ref
            for tier, tname in enumerate(TIERS):
                entry = ref + sign * tier * cfg["price_tick"]
                res = _simulate_outcome(
                    bars, i, q.draft.direction, entry, q.draft.stop["level"],
                    q.draft.invalidation["type"], q.draft.invalidation["level"],
                    horizon)
                src[f"{tname}_entry"] = entry
                src[f"{tname}_outcome"] = res["outcome"]
                src[f"{tname}_exit"] = res["exit_price"]
                src[f"{tname}_hold"] = res["hold_bars"]
                src[f"{tname}_gross_r"] = res["gross_r"]
                if res["gross_r"] is not None:
                    risk = abs(entry - q.draft.stop["level"])
                    fee = (commission_per_side(entry, meta)
                           + commission_per_side(res["exit_price"], meta))
                    src[f"{tname}_fee_r"] = fee / (risk * meta["multiplier"])
                    src[f"{tname}_net_r"] = res["gross_r"] - src[f"{tname}_fee_r"]
                else:
                    src[f"{tname}_fee_r"] = None
                    src[f"{tname}_net_r"] = None
        pending = still

        # ---- B. 收盘基失效（挂单期 pre-trigger invalid）----
        alive: list[Pending] = []
        for q in pending:
            inv = q.draft.invalidation
            crossed = (bar.close_price < inv["level"] if inv["type"] == "close_below"
                       else bar.close_price > inv["level"])
            if crossed:
                rows[q.row_idx]["outcome"] = "PRE_INVALID"
                if q.draft.category in COOLDOWN_CATEGORIES:
                    invalid_log.append({"level": inv["level"], "bar_time": bar.datetime})
            else:
                alive.append(q)
        pending = alive

        # ---- B2. 过期 ----
        alive = []
        for q in pending:
            q.expire_left -= 1
            if q.expire_left <= 0:
                rows[q.row_idx]["outcome"] = "EXPIRED"
            else:
                alive.append(q)
        pending = alive

        # ---- C. 检测（新挂单）----
        for p in pivots.update(bar):
            levels.add("prior_high" if p.kind == "H" else "prior_low", p.price)
            levels.add("range_top" if p.kind == "H" else "range_bottom", p.price)
        window = bars[max(0, i - BARS_WINDOW + 1): i + 1]
        ctx = SignalContext(bars=window, atr=atr.value, ema=ema, pivots=pivots,
                            levels=levels, cfg=cfg, direction="both", context_tag=tag,
                            now=bar.datetime, price_tick=cfg["price_tick"],
                            fake_log=fake_log, invalid_log=invalid_log)
        seen: set = set()
        for det in detectors:
            for d in det.detect(ctx):
                key = (d.signal_id, d.direction,
                       round(d.trigger["level"] / cfg["price_tick"]))
                if key in seen:
                    continue
                seen.add(key)
                row = {
                    "symbol": prod, "signal_id": d.signal_id, "family": d.family,
                    "category": d.category, "rank": d.rank, "direction": d.direction,
                    "order_type": d.order_type,
                    "bar_time": bar.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                    "trigger_type": d.trigger["type"],
                    "trigger_level": d.trigger["level"], "trigger_ref": d.trigger["ref"],
                    "stop_level": d.stop["level"], "stop_ref": d.stop["ref"],
                    "invalidation_type": d.invalidation["type"],
                    "invalidation_level": d.invalidation["level"],
                    "context_tag": tag, "quality_pass": int(passes_quality(ctx, d)),
                    "note": d.note,
                    "in_sample": int(bar.datetime.strftime("%Y-%m-%d %H:%M:%S") < SPLIT_ISO),
                    "outcome": "PENDING", "fill_ref": None,
                }
                for tname in TIERS:
                    row[f"{tname}_entry"] = None
                    row[f"{tname}_outcome"] = None
                    row[f"{tname}_exit"] = None
                    row[f"{tname}_hold"] = None
                    row[f"{tname}_gross_r"] = None
                    row[f"{tname}_fee_r"] = None
                    row[f"{tname}_net_r"] = None
                rows.append(row)
                pending.append(Pending(len(rows) - 1, d, i, cfg["expire_bars_exec"]))

        # ---- D. levels 有效性推进 ----
        levels.on_bar_close(bar, atr.value, cfg["level_touch_atr"])

    for q in pending:                                # 数据尽头仍未决
        rows[q.row_idx]["outcome"] = "OPEN"
    return rows, context_rows, {"bars": len(bars), "drafts": len(rows)}


def _agg(group: list[dict], tier: str) -> dict:
    """tier 口径聚合：分子只用该档成交行；分母（signals）= 全部草稿。"""
    triggered = [r for r in group if r["outcome"] == "TRIGGERED"]
    okey, rkey, hkey = f"{tier}_outcome", f"{tier}_net_r", f"{tier}_hold"
    filled = [r for r in triggered if r[okey] not in ("OPEN", "NO_RISK", None)]
    decided = [r for r in filled if r[okey] in ("T1", "SL")]
    wins = [r for r in decided if r[okey] == "T1"]
    with_r = [r for r in filled if r[rkey] is not None]
    pos = [r for r in with_r if r[rkey] > 0]
    neg = [r for r in with_r if r[rkey] < 0]
    holds = [r[hkey] for r in filled if r[hkey]]
    return {
        "signals": len(group),
        "triggered": len(triggered),
        "trigger_rate": round(len(triggered) / len(group), 4) if group else 0.0,
        "win_rate": round(len(wins) / len(decided), 4) if decided else None,
        "avg_net_r": round(sum(r[rkey] for r in with_r) / len(with_r), 4)
        if with_r else None,
        "payoff": (round((sum(r[rkey] for r in pos) / len(pos))
                         / abs(sum(r[rkey] for r in neg) / len(neg)), 3)
                   if pos and neg else None),
        "avg_hold_bars": round(sum(holds) / len(holds), 1) if holds else None,
        "invalid_exit_share": (round(sum(1 for r in filled if r[okey] == "INVALID")
                                     / len(filled), 4) if filled else None),
    }


DETAIL_COLS = ["symbol", "signal_id", "family", "category", "rank", "direction",
               "order_type", "bar_time", "trigger_type", "trigger_level",
               "trigger_ref", "stop_level", "stop_ref", "invalidation_type",
               "invalidation_level", "context_tag", "quality_pass", "note",
               "in_sample", "outcome", "fill_ref"]
TIER_COLS = [f"{t}_{k}" for t in TIERS
             for k in ("entry", "outcome", "exit", "hold", "gross_r", "fee_r", "net_r")]


def write_outputs(all_rows: list[dict], all_ctx: list[dict], notes: list[str]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    ctx_dir = os.path.join(OUT_DIR, "context_tags")
    os.makedirs(ctx_dir, exist_ok=True)

    with open(os.path.join(OUT_DIR, "signals_detail.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DETAIL_COLS + TIER_COLS)
        w.writeheader()
        w.writerows([{k: r.get(k) for k in DETAIL_COLS + TIER_COLS} for r in all_rows])

    by_prod: dict[str, list[dict]] = defaultdict(list)
    for r in all_ctx:
        by_prod[r["symbol"]].append(r)
    for prod, crs in by_prod.items():
        with open(os.path.join(ctx_dir, f"{prod}_context_tags.csv"), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["datetime", "symbol", "context_tag"])
            w.writeheader()
            w.writerows(crs)

    _write_summaries(all_rows)
    write_report(all_rows, all_ctx, sorted(by_prod), notes)


def _write_summaries(all_rows: list[dict]) -> None:
    """summary_by_signal_id + summary_by_year（HO003 B：by_year 升至 p0/p1/p2 全档位）。"""
    # summary_by_signal_id：signal_id × symbol(含 ALL) × tier × sample
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for r in all_rows:
        sample = "in_sample" if r["in_sample"] else "out_sample"
        for tier in TIERS:
            buckets[(r["signal_id"], r["symbol"], tier, sample)].append(r)
            buckets[(r["signal_id"], r["symbol"], tier, "ALL")].append(r)
            buckets[(r["signal_id"], "ALL", tier, sample)].append(r)
            buckets[(r["signal_id"], "ALL", tier, "ALL")].append(r)
    agg_cols = list(_agg([], "p0").keys())
    with open(os.path.join(OUT_DIR, "summary_by_signal_id.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["signal_id", "symbol", "cost_tier", "sample"] + agg_cols)
        for (sid, sym, tier, sample), grp in sorted(buckets.items()):
            w.writerow([sid, sym, tier, sample] + list(_agg(grp, tier).values()))

    # summary_by_year：year × signal_id × tier
    yb: dict[tuple, list[dict]] = defaultdict(list)
    for r in all_rows:
        for tier in TIERS:
            yb[(r["bar_time"][:4], r["signal_id"], tier)].append(r)
    with open(os.path.join(OUT_DIR, "summary_by_year.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "signal_id", "cost_tier"] + agg_cols)
        for (year, sid, tier), grp in sorted(yb.items()):
            w.writerow([year, sid, tier] + list(_agg(grp, tier).values()))


def write_report(all_rows: list[dict], all_ctx: list[dict], prods: list[str],
                 notes: list[str]) -> None:
    lines = ["# 基线回测报告（轮次 0）", ""]
    lines += [f"- 生成：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}"
              f"；品种：{'/'.join(prods)}；信号草稿数：{len(all_rows)}", ""]
    lines += ["## 口径与假设", ""]
    lines += [
        "- 成本三档 p0/p1/p2 = 成交参考价 +0/+1/+2 tick（按方向不利侧）",
        f"- 佣金 = 保证金×万3 双边（DEC003：{FEE_RATE}×价×乘数×保证金率，全品种全档位）",
        "- 保证金率默认假设（可调）：RB=0.10 CU=0.10 AG=0.12 M=0.08 MA=0.09 TA=0.09",
        f"- T1 定义 = {T1_MULT}R 目标价（全表一致）；SL = stop_level；同根双触保守先 SL",
        f"- 前瞻 horizon = {HORIZON} 根；数据尽头未决记 OPEN（不计胜率）",
        "- 换月拼接：_detect_and_splice（后复权），2015-01-01 起",
        "- 挂单：expire_bars_exec=3；触发=下一根开盘优先，否则盘中触及；触发优先于收盘失效",
        "- 判定侧 context v0 规则（逐根，point-in-time）：",
        "  1. breakout：收盘突破前 40 根区间边缘 ± 0.1×ATR",
        "  2. trend_strong：EMA20 五根斜率与 (close-EMA20) 同向且 |斜率| >= 0.25×ATR",
        "  3. trend_channel：同向但 |斜率| < 0.25×ATR",
        "  4. range：|close-EMA20| <= 0.25×ATR 且 40 根区间宽 <= 4×ATR",
        "  5. reversal：斜率与 (close-EMA20) 异号",
        "  6. 其余 → trend_channel（中性）",
        "- 基线只跑现网 9 detector（h1_l1/w_m 默认关闭，未参与）",
        "- 与生产差异：基线无指令池过滤（全类别运行）；levels 由确认摆动点直接播种"
        "（含 range_top/bottom 镜像），生产 levels 来自选品指令",
        "",
    ]
    lines += notes or []
    lines += ["", "## 汇总（tier=p1，含佣金 net_R，ALL 品种池）", ""]
    lines += ["| signal_id | sample | signals | trigger_rate | win_rate | avg_net_r |"
              " payoff | avg_hold | invalid_exit |",
              "|---|---|---|---|---|---|---|---|---|"]
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for r in all_rows:
        sample = "in" if r["in_sample"] else "out"
        buckets[(r["signal_id"], sample)].append(r)
        buckets[(r["signal_id"], "ALL")].append(r)
    for (sid, sample), grp in sorted(buckets.items()):
        a = _agg(grp, "p1")
        lines.append(f"| {sid} | {sample} | {a['signals']} | {a['trigger_rate']} | "
                     f"{a['win_rate']} | {a['avg_net_r']} | {a['payoff']} | "
                     f"{a['avg_hold_bars']} | {a['invalid_exit_share']} |")
    tag_set = sorted({r["context_tag"] for r in all_ctx if r["context_tag"]})
    lines += ["", "## context_tag 分布（判定侧 v0，逐根）", "",
              "| symbol | " + " | ".join(tag_set) + " |",
              "|" + "---|" * (len(tag_set) + 1)]
    ctx_by_prod: dict[str, list[dict]] = defaultdict(list)
    for r in all_ctx:
        ctx_by_prod[r["symbol"]].append(r)
    for prod in prods:
        c = Counter(r["context_tag"] for r in ctx_by_prod.get(prod, []))
        n = sum(c.values()) or 1
        cells = [f"{c.get(t, 0) / n * 100:.1f}%" for t in tag_set]
        lines.append(f"| {prod} | " + " | ".join(cells) + " |")
    lines += ["", "## 已知局限", "",
              "- 判定侧 context 为基线自建 v0 规则，非生产指令实际标签；"
              "RS012 混淆矩阵（验证队列 #1）将检验其准确率",
              "- 保证金率为固定近似（历史随交易所调整），佣金敏感性可用 margin_rate 复算",
              "- 基线为信号级研究口径，未含生产指令池/优先级/合并逻辑", ""]
    with open(os.path.join(OUT_DIR, "baseline_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _run_export_context(prods: list[str]) -> None:
    """HO003 交付：context v1 序列导出 + 验收自检（不动已交付的信号基线）。"""
    ctx_dir = os.path.join(OUT_DIR, "context_tags")
    os.makedirs(ctx_dir, exist_ok=True)
    all_rows: list[dict] = []
    for prod in prods:
        if prod not in PRODUCTS:
            raise SystemExit(f"未知品种 {prod}")
        rows, stats = export_context_only(prod, PRODUCTS[prod])
        all_rows.extend(rows)
        with open(os.path.join(ctx_dir, f"{prod}_context_tags.csv"), "w",
                  newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "datetime", "symbol", "context_tag", "strict_range"])
            w.writeheader()
            w.writerows(rows)
        print(f"[ctx] {prod}: bars={stats['bars']} rows={stats['rows']}")
    _write_context_acceptance(all_rows)


def _write_context_acceptance(rows: list[dict]) -> None:
    """HO003 验收预自检：range 触发占比 ≥8%、breakout 中位持续期 ≥5 根。"""
    n = len(rows) or 1
    dist = Counter(r["context_tag"] for r in rows)
    strict_share = sum(int(r.get("strict_range") or 0) for r in rows) / n

    def run_lengths(tag: str) -> list[int]:
        out: list[int] = []
        cur = 0
        for r in rows:
            if r["context_tag"] == tag:
                cur += 1
            elif cur:
                out.append(cur)
                cur = 0
        if cur:
            out.append(cur)
        return out

    bo = sorted(run_lengths("breakout"))
    bo_median = bo[len(bo) // 2] if bo else 0
    range_share = dist.get("range", 0) / n
    ok = range_share >= 0.08 and bo_median >= 5
    lines = [
        "# context v1 导出自检（HO003 预检；正式验收=研究侧重跑两脚本）", "",
        f"- 总行数：{len(rows)}（{','.join(sorted({r['symbol'] for r in rows}))}）",
        f"- 分布：{dict(sorted(dist.items()))}",
        f"- range 触发占比：{range_share * 100:.1f}%（验收 ≥8%）",
        f"- breakout 块数：{len(bo)}，中位持续期：{bo_median} 根（验收 ≥5）",
        f"- strict_range 占比：{strict_share * 100:.1f}%",
        f"- 预检：{'PASS' if ok else 'CHECK_NEEDED'}",
    ]
    path = os.path.join(OUT_DIR, "context_v1_acceptance.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"[done] -> {path}")


def _run_resummarize() -> None:
    """HO003 B：从既有 signals_detail.csv 重建汇总（by_year 升至全档位）。"""
    src = os.path.join(OUT_DIR, "signals_detail.csv")
    if not os.path.exists(src):
        raise SystemExit(f"missing {src}（先跑 --mode full 生成明细）")
    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    for r in rows:
        r["in_sample"] = int(r["in_sample"])
        for t in TIERS:
            for k in ("entry", "exit", "gross_r", "fee_r", "net_r"):
                r[f"{t}_{k}"] = num(r.get(f"{t}_{k}"))
            h = r.get(f"{t}_hold")
            r[f"{t}_hold"] = int(h) if h not in (None, "", "None") else None
    _write_summaries(rows)
    print(f"[done] resummarized {len(rows)} drafts "
          f"(summary_by_year 升至 p0/p1/p2 全档位, HO003 B)")


def main() -> None:
    ap = argparse.ArgumentParser(description="HO001 baseline backtest (offline)")
    ap.add_argument("--mode", choices=["full", "export-context", "resummarize"],
                    default="full",
                    help="full=全量回测；export-context=HO003 context v1 序列导出"
                         "（不重跑信号）；resummarize=HO003 B 由明细重建汇总")
    ap.add_argument("--products", default=",".join(PRODUCTS),
                    help="逗号分隔品种代码，如 RB,CU")
    ap.add_argument("--horizon", type=int, default=HORIZON)
    args = ap.parse_args()

    prods = [p.strip().upper() for p in args.products.split(",") if p.strip()]
    if args.mode == "export-context":
        _run_export_context(prods)
        return
    if args.mode == "resummarize":
        _run_resummarize()
        return

    all_rows: list[dict] = []
    all_ctx: list[dict] = []
    notes: list[str] = ["## 运行清单", ""]
    for prod in prods:
        if prod not in PRODUCTS:
            raise SystemExit(f"未知品种 {prod}（可用：{', '.join(PRODUCTS)}）")
        meta = PRODUCTS[prod]
        rows, ctx, stats = run_product(prod, meta, args.horizon)
        all_rows.extend(rows)
        all_ctx.extend(ctx)
        notes.append(f"- {prod}.{meta['exchange']}: bars={stats['bars']}, "
                     f"草稿数={stats['drafts']}")
    notes.append("")
    write_outputs(all_rows, all_ctx, notes)
    print(f"[done] products={prods} rows={len(all_rows)} ctx={len(all_ctx)} -> {OUT_DIR}")


if __name__ == "__main__":
    main()
