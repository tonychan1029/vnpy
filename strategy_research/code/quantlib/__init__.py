# RESEARCH ONLY - quantlib 入口
"""quantlib：形态与信号量化工具库。

行布局约定：bars 为 list[list]，每行 [dt, o, h, l, c, v, oi]。
全库统一。

模块清单：
- structure: 趋势形态/摆动点/区间边界/支撑三法 ✅
- gap: 缺口检测/分类/关键位 ✅
- pullback: 回调质量（回撤比例/MA贴近/支撑有效性）✅
- entry_signal: 入场信号（突破确认/H2L2/pin bar/反包/近均十字星）✅
- exhaustion: 衰竭信号（楔形三推/量价背离/抛售高潮）✅

设计原则：纯函数（无副作用）；同接口不同实现可切换；每函数有 docstring。
"""

from quantlib.structure import (
    find_swing_points,
    detect_trend_zigzag,
    detect_trend_ema_slope,
    classify_trend,
    find_range_boundary,
    near_support,
    near_resistance,
    kline_density_zone,
)
