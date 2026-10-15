# RESEARCH ONLY - 未获用户批准不得正式运行
"""DEC003+1tick 可交易口径——单一成本实现（阶段0-2；ROADMAP §1A 0-2）。

口径（DEC003，用户确认维持）：
  佣金 = 保证金 × 万3，双边（开+平各一次 → 往返 = 保证金率 × 0.0003 × 2）
滑点 = 1 tick/边（往返 2 tick），按 tick_size/price 折算为名义比例。

保证金率/tick 为 2026 近似值（结算参数以工程为准）；缺表品种保证金率默认
10%、tick 滑点按 0.03% 名义/边近似并在报告中标注精度降级。

用法：
  from analysis.cost import cost_return
  c = cost_return("RB", price=3560.0)   # 往返成本占名义比例
"""

from __future__ import annotations

COMMISSION_PER_SIDE = 0.0003          # 万3
DEFAULT_MARGIN_RATE = 0.10
UNKNOWN_TICK_SLIP_PER_SIDE = 0.0003   # 缺 tick 表品种的名义近似

MARGIN_RATE = {
    "RB": 0.12, "CU": 0.10, "AL": 0.10, "AG": 0.10, "M": 0.08,
    "Y": 0.09, "P": 0.09, "TA": 0.08, "MA": 0.08, "SR": 0.07, "IF": 0.12,
}

TICK_SIZE = {
    "RB": 1.0, "CU": 10.0, "AL": 5.0, "AG": 1.0, "M": 1.0,
    "Y": 2.0, "P": 2.0, "TA": 2.0, "MA": 1.0, "SR": 1.0, "IF": 0.2,
}


def cost_return(sym: str, price: float) -> float:
    """往返成本占名义价值比例（佣金双边 + 1tick/边 滑点）。"""
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    mr = MARGIN_RATE.get(sym, DEFAULT_MARGIN_RATE)
    commission = mr * COMMISSION_PER_SIDE * 2
    tick = TICK_SIZE.get(sym)
    slip = (2 * tick / price) if tick is not None \
        else 2 * UNKNOWN_TICK_SLIP_PER_SIDE
    return commission + slip


def net_of_cost(sym: str, price: float, gross: float) -> float:
    """方向调整后的毛收益 → 扣成本净收益（乘法口径）。"""
    return (1.0 + gross) * (1.0 - cost_return(sym, price)) - 1.0
