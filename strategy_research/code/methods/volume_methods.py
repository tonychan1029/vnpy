# RESEARCH ONLY - 未获用户批准不得正式运行
"""MLIB 量能方法研究级实现（M-VR-002 v1、M-DV-002 v1）。

定义以 MLIB 登记册为单一事实来源；本版实现基础归一化，
时段修正（M-VR-002 规则3）预留接口。与工程代码零依赖。
"""

from __future__ import annotations

from .pa_methods import SwingPoint


def m_vr_002_rvol(volumes: list[float], t: int, n: int = 20,
                  rollover_flags: set[int] | None = None,
                  clamp_hi: float = 10.0) -> float | None:
    """M-VR-002 相对量：volume_t / mean(前 n 根)。

    rollover_flags：换月标记根集合（含其后 1 根应一并传入调用方剔除）。
    基准窗口内含换月根不足半数才计算，否则返回 None（数据不足）。
    """
    if rollover_flags is None:
        rollover_flags = set()
    lo, hi = max(0, t - n), t
    base = [v for i, v in enumerate(volumes[lo:hi], start=lo) if i not in rollover_flags]
    if len(base) < n * 0.5:
        return None
    mean_v = sum(base) / len(base)
    if mean_v <= 0:
        return None
    rvol = volumes[t] / mean_v
    return min(rvol, clamp_hi)


def m_dv_002_new_low_shrink(highs: list[float], lows: list[float],
                            volumes: list[float], pivots: list[SwingPoint],
                            rvol_at_new_low: float | None,
                            shrink_ratio: float = 0.8) -> bool | None:
    """M-DV-002 新低缩量（底背离基础判据 v1）。

    条件：最近摆动低点 L2 价格 < 前一低点 L1（创新低），且 L2 根的
    rvol_adj < shrink_ratio x L1 根的 rvol_adj -> 卖压衰竭（True）。
    rvol 不足（None）-> None（不判定）。
    """
    lp = [p for p in pivots if p.kind == "L"]
    if len(lp) < 2 or rvol_at_new_low is None:
        return None
    l1, l2 = lp[-2], lp[-1]
    if l2.price >= l1.price:
        return False
    # L1 根相对量以调用方传入同窗口计算；此处用 volumes 在两 pivot 邻域的均值近似
    i1 = l1.index
    base1 = volumes[max(0, i1 - 3): i1 + 1]
    rvol_l1 = (sum(base1) / len(base1)) if base1 else None
    if not rvol_l1:
        return None
    return rvol_at_new_low < shrink_ratio * rvol_l1


# ------------------------- M-EX-003 / M-DV-001（v1，2026-10-12 定稿） ------

def m_ex_003_volume_exhaustion(bar, rvol_adj: float | None,
                               shrink: float = 0.8) -> bool | None:
    """M-EX-003 量能衰竭K：rvol_adj < shrink 且收盘靠反转侧 1/3。

    bar 需 open/high/low/close。rvol 缺失 -> None（不判定）。
    连续增强（两根连缩）由调用方按前一根结果叠加。
    """
    if rvol_adj is None:
        return None
    body = abs(bar.close_price - bar.open_price)
    rng = bar.high_price - bar.low_price
    if rng <= 0:
        return False
    reversal_side = bar.close_price >= bar.low_price + rng / 3  # 多头口径
    return rvol_adj < shrink and reversal_side


def m_dv_001_rebound_volume_divergence(rebound_rvols: list[float],
                                       probe_rvols: list[float],
                                       ratio: float = 1.5,
                                       last_probe_shrink: float = 0.8) -> bool | None:
    """M-DV-001 反弹放量+探底缩量（双条件底背离 v1）。

    rebound_rvols/probe_rvols：最近一段下探中反弹K与探底K的 rvol_adj 序列。
    条件：均值(rebound) / 均值(probe) >= ratio 且 末根探底 <= last_probe_shrink。
    任一序列为空 -> None。
    """
    if not rebound_rvols or not probe_rvols:
        return None
    rb = sum(rebound_rvols) / len(rebound_rvols)
    pb = sum(probe_rvols) / len(probe_rvols)
    if pb <= 0:
        return None
    return rb / pb >= ratio and probe_rvols[-1] <= last_probe_shrink
