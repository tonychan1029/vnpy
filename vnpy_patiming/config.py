"""Central parameter table. Every threshold used by detectors lives here."""

from __future__ import annotations

import copy

TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    # 1d:日线波段(2026-10-13)。selection 基周期语义,倒计时按 1d 收线 K 锚定;
    # BarSynthesizer 1440 分钟窗为自然日聚合,valid_bars=12 ≈ 12 个自然日(偏保守)。
    "1d": 1440,
}

REASON_CODES = {
    "BREAKOUT_WATCH",
    "TREND_FOLLOW",
    "RANGE_FADE",
    "REVERSAL_WATCH",
    "DISCRETIONARY",
}

CONTEXT_TAGS = {"trend_strong", "trend_channel", "range", "breakout", "reversal"}

SIGNAL_CATEGORIES = {
    "breakout",
    "fake_breakout",
    "second_breakout",
    "ema_pullback",
    "structure_pullback",
    "range_edge",
    "h2_l2",
    "double_top_bottom",
    "wedge",
    "h1_l1",
    "w_m",
}

DIRECTIONS = {"long", "short", "both"}

REASON_DEFAULT_SIGNALS: dict[str, list[str]] = {
    "BREAKOUT_WATCH": ["breakout", "fake_breakout", "second_breakout"],
    # HO006 后续（2026-10-15 决议①）：ema_pullback 退役移除
    "TREND_FOLLOW": ["structure_pullback", "h1_l1"],
    "RANGE_FADE": ["range_edge", "fake_breakout", "w_m"],
    "REVERSAL_WATCH": ["w_m"],
    "DISCRETIONARY": [],
}

DEFAULT_CONFIG: dict = {
    "poll_interval_s": 2.0,
    "default_valid_bars": 12,
    "min_survival_minutes": 1,
    "quota_per_source": 20,
    "quota_total_active": 100,
    "symbol_whitelist": None,  # None = allow any well-formed symbol
    "context_whitelist": None,  # None = allow known CONTEXT_TAGS only
    "llm_params_locked": True,
    "key_level_pct_band": 0.10,  # key_levels sanity band vs last price
    "atr_period": 14,
    "ema_period": 20,
    "pivot_k": 2,
    "overlap_window": 5,
    "overlap_max": 0.85,
    "buffer_ticks": 2,
    "price_tick": 1.0,
    "level_touch_atr": 0.25,
    "breakout_min_atr": 0.10,
    "breakout_body_min": 0.6,
    "fake_poke_atr": 0.05,
    "fake_stop_atr": 0.25,
    "second_breakout_window": 10,
    "max_stop_atr": 2.0,
    "min_stop_atr": 0.5,
    "bar_min_atr": 0.5,
    "bar_max_atr": 3.0,
    "gap_fill_bars": 5,
    "h2_window_bars": 10,
    "dbl_max_sep_bars": 40,
    "dbl_tol_atr": 0.3,
    "wedge_decay_ratio": 0.67,
    "wedge_body_max": 0.45,
    "pb_retest_window": 20,
    "pb_cooldown_bars": 10,
    "require_approval": False,
    "tick_fallback_on_stale": True,
    "require_approval": False,
    "expire_bars_exec": 3,
    "warmup_min_exec": 42,  # max(3 * atr_period, 10)
    "warmup_min_selection": 1,
    "freshness_interval_factor": 5,
    "outbox_max_attempts": 5,
    "outbox_backoff_base_s": 0.2,
    "request_min_interval_s": 0.0,
    "expiring_soon_bars": 3,
    "default_context_tag": "breakout",
    # ---- HO002 新增（RS004 判据）；两个 detector 默认关闭，经配置开启 ----
    "enable_h1_l1": False,
    "h1_lookback": 20,
    "h1_ema_tol": 0.5,
    "enable_w_m": False,
    "wm_min_sep_bars": 5,
    "wm_max_sep_bars": 30,
    "wm_tol_atr": 0.5,
    "wm_neck_min_atr": 1.0,
    # ---- HO006 后续（2026-10-15 决议①）：EMA20 接刀退役，默认关闭 ----
    "enable_ema_pullback": False,
}


def build_config(overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if overrides:
        cfg.update(overrides)
    cfg["warmup_min_exec"] = max(3 * int(cfg["atr_period"]), 10)
    if overrides and "warmup_min_exec" in overrides:
        cfg["warmup_min_exec"] = int(overrides["warmup_min_exec"])
    return cfg
