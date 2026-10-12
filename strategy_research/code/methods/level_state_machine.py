# RESEARCH ONLY - 未获用户批准不得正式运行
"""MLIB 关键位状态机研究级实现（M-LV-003 v1，RS010 模型）。

定义以 MLIB 登记册为单一事实来源；与工程代码零依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LevelState(str, Enum):
    FRESH = "fresh"
    PROFIT_BREAK = "profit_break"
    FAKE_BREAK = "fake_break"
    FAIL_BREAK = "fail_break"


@dataclass
class LevelRecord:
    """一个关键位的记录：价位 + 状态 + 状态生效起始序号。"""
    price: float
    state: LevelState = LevelState.FRESH
    state_since: int = 0
    events: list = field(default_factory=list)   # 事件审计轨迹


def classify_break_event(path_high: float, path_low: float, level: float,
                         atr: float, direction: str) -> str:
    """突破后事件三分类（M-LV-003 判据核心）。

    path_high/path_low：突破信号之后的 K 线路径极值。
    - profit_break：顺势走出 >= 1xATR
    - fake_break：触及位但未走出 0.5xATR 且收回位另一侧
    - fail_break：走出 [0.5, 1) xATR 后收回（中间态归失败/无跟随族）
    """
    if direction == "long":
        follow = path_high - level
        pulled = path_low < level
    else:
        follow = level - path_low
        pulled = path_high > level
    if follow >= 1.0 * atr:
        return "profit_break"
    if pulled:
        return "fake_break" if follow < 0.5 * atr else "fail_break"
    return "pending"   # 尚未定级：既未走足也未收回，继续观察


def apply_event(level_rec: LevelRecord, event: str, bar_index: int,
                state_ttl: int = 20) -> None:
    """事件落位：更新状态与审计轨迹；TTL 超时由 age_state 负责。"""
    level_rec.state = LevelState(event)
    level_rec.state_since = bar_index
    level_rec.events.append((bar_index, event))


def age_state(level_rec: LevelRecord, bar_index: int,
              state_ttl: int = 20) -> LevelState:
    """状态时效：超 TTL 回落 fresh。"""
    if (level_rec.state != LevelState.FRESH
            and bar_index - level_rec.state_since > state_ttl):
        level_rec.state = LevelState.FRESH
    return level_rec.state


def signal_weight_for(state: LevelState, signal_family: str) -> float:
    """后继规则表：位状态 x 信号族 -> 权重系数（v1 线性表）。

    fresh=1.0；降权 0.5；升权 1.5。权重仅供编排层（S-004）做排序，
    不直接等于仓位。
    """
    if state == LevelState.FRESH:
        return 1.0
    if state == LevelState.PROFIT_BREAK:
        return 0.5 if signal_family in ("breakout", "second_breakout") else 1.0
    if state == LevelState.FAKE_BREAK:
        return 1.5 if signal_family == "second_breakout" else 1.0
    if state == LevelState.FAIL_BREAK:
        return 1.5 if signal_family == "fake_breakout" else 1.0
    return 1.0
