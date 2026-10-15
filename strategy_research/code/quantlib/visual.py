# RESEARCH ONLY - quantlib.visual：视觉检验工具
"""生成 K 线图 + 量化函数标注叠加图，供视觉验证形态识别准确度。

用法：
  from quantlib.visual import plot_with_overlays
  plot_with_overlays(bars, overlays={
      "swing_points": [...],       # 摆动点列表
      "trend_zones": [...],        # 趋势区间
      "support_resistance": [...], # 支撑/压力线
      "gap_zones": [...],          # 缺口区域
      "entry_signals": [...],      # 入场信号箭头
  })
输出 PNG 图表到 assets/RS021/visual_check/
"""

import os


def plot_with_overlays(bars, overlays, title, out_path):
    """K 线 + 量化标注叠加图。

    bars: [[dt, o, h, l, c, v, oi]]
    overlays: dict，key 为标注类型
      "swing_H": [(idx, price)]  — 摆动高点（红色三角↑）
      "swing_L": [(idx, price)]  — 摆动低点（绿色三角↓）
      "support_lines": [(idx0, idx1, price)]  — 支撑线（蓝色横线）
      "resistance_lines": [(idx0, idx1, price)]  — 压力线（红色横线）
      "gap_zones": [(idx0, idx1, top, bottom)]  — 缺口区域（灰色矩形）
      "trend_zones": [(idx0, idx1, "多头"/"空头")]  — 趋势背景（绿/红色半透明）
      "entry_arrows": [(idx, price, "long"/"short")]  — 入场信号箭头
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
        "Droid Sans Fallback", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    n = len(bars)
    fig, ax = plt.subplots(figsize=(16, 8))

    # K 线
    for i in range(n):
        b = bars[i]
        color = "#d33" if b[4] >= b[1] else "#2a7"
        # 影线
        ax.plot([i, i], [b[4], b[3]], color=color, lw=0.7, zorder=2)
        # 实体
        body_lo = min(b[1], b[4])
        body_h = max(abs(b[4] - b[1]), 0.01)
        face = "#d33" if b[4] >= b[1] else "#2a7"
        ax.add_patch(Rectangle((i - 0.35, body_lo), 0.7, body_h,
                               facecolor=face, edgecolor=color, zorder=3))

    # 叠加层
    for name, items in overlays.items():
        if name == "swing_H":
            for idx, price in items:
                ax.annotate("▼", (idx, price), color="red", fontsize=8,
                            ha="center", va="bottom", zorder=5)
        elif name == "swing_L":
            for idx, price in items:
                ax.annotate("△", (idx, price), color="green", fontsize=8,
                            ha="center", va="top", zorder=5)
        elif name == "support_lines":
            for i0, i1, price in items:
                ax.plot([i0, i1], [price, price], color="#06c", lw=1,
                        ls="--", alpha=0.7, zorder=1)
        elif name == "resistance_lines":
            for i0, i1, price in items:
                ax.plot([i0, i1], [price, price], color="#c33", lw=1,
                        ls="--", alpha=0.7, zorder=1)
        elif name == "gap_zones":
            for i0, i1, top, bot in items:
                ax.fill_between([i0, i1], bot, top, color="#888", alpha=0.2, zorder=1)
        elif name == "trend_zones":
            for i0, i1, label in items:
                color = "#2a7" if "多" in label else "#d33" if "空" in label else "#cc8"
                ax.axvspan(i0, i1, color=color, alpha=0.08, zorder=0)
        elif name == "entry_arrows":
            for idx, price, d in items:
                if d == "long":
                    ax.annotate("↑B", (idx, price), color="#0c0", fontsize=9,
                                fontweight="bold", ha="center", va="top", zorder=5)
                else:
                    ax.annotate("↓S", (idx, price), color="#c00", fontsize=9,
                                fontweight="bold", ha="center", va="bottom", zorder=5)

    ax.set_title(title, fontsize=14)
    ax.set_ylabel("价格")
    ax.set_xlim(-1, n)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
