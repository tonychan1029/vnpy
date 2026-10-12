# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS012 混淆矩阵 runner（预测侧）——context_tag 序列到达后即插即跑。

输入契约（R2，写入 ENVIRONMENT）：
  strategy_research/assets/RS012/incoming/predictions.csv
  列: datetime,symbol,pred_label   （pred_label ∈ BREAKOUT/RANGE/REVERSAL/
  TREND_DN/TREND_UP/UNDEFINED；datetime 与 GT 标签文件同格式）
流程：按品种加载 GT（assets/RS012/{sym}_gt_labels.csv），按 (symbol,datetime)
内连接，调 context_eval.agreement_matrix，输出混淆矩阵 + 预注册判读带。
用法：python rs012_confusion.py [predictions.csv 路径，缺省用上述契约路径]
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from methods.context_eval import agreement_matrix  # noqa: E402

GT_DIR = ROOT.parent / "assets" / "RS012"
DEFAULT_IN = GT_DIR / "incoming" / "predictions.csv"
SYMBOLS = ("RB", "CU", "AG", "M", "MA", "TA")


def load_gt(sym: str) -> dict:
    p = GT_DIR / f"{sym}_gt_labels.csv"
    if not p.exists():
        return {}
    with p.open(newline="", encoding="utf-8") as f:
        return {r["datetime"]: r["gt_label"] for r in csv.DictReader(f)}


def main(argv):
    in_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_IN
    if not in_path.exists():
        print(f"[missing] 预测文件不存在: {in_path}")
        print("等待工程侧 R2 交付（context_tag 序列导出）。契约见本文件头注释。")
        return 1
    gts_all = {s: load_gt(s) for s in SYMBOLS}
    pairs = defaultdict(lambda: ([], []))          # sym -> (gts, preds)
    with in_path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sym = r.get("symbol", "").upper()
            gt = gts_all.get(sym, {}).get(r["datetime"])
            if gt is not None:
                pairs[sym][0].append(gt)
                pairs[sym][1].append(r["pred_label"])
    lines = ["# RS012 混淆矩阵报告（context_tag 判定 vs 操作性真值 GT v1.1）", "",
             f"- 预测文件: `{in_path}`", ""]
    total_g, total_p = [], []
    for sym in SYMBOLS:
        gts, preds = pairs.get(sym, ([], []))
        if not gts:
            lines.append(f"## {sym}：无匹配样本")
            continue
        r = agreement_matrix(gts, preds)
        lines.append(f"## {sym}（n={len(gts)}）")
        labels = list(r["matrix"].keys())
        lines.append("| GT\\PRED | " + " | ".join(labels) + " |")
        lines.append("|---|" + "---|" * len(labels))
        for g in labels:
            lines.append(f"| {g} | " +
                         " | ".join(str(r["matrix"][g][p]) for p in labels) +
                         " |")
        lines.append("")
        total_g.extend(gts)
        total_p.extend(preds)
    if total_g:
        r = agreement_matrix(total_g, total_p)
        lines.append(f"## 合并（n={len(total_g)}）")
        labels = list(r["matrix"].keys())
        lines.append("| GT\\PRED | " + " | ".join(labels) + " |")
        lines.append("|---|" + "---|" * len(labels))
        for g in labels:
            lines.append(f"| {g} | " +
                         " | ".join(str(r["matrix"][g][p]) for p in labels) +
                         " |")
        lines.append("")
        lines.append("## 预注册判读（勿临场修改）")
        rp = r["top_pred_precision"].get("RANGE")
        if rp is None:
            lines.append("- RANGE 类样本不足，无法判读")
        elif rp >= 0.60:
            lines.append(f"- RANGE top-pred 精确率 {rp:.1%} ≥60% → **context_tag 维持可用**")
        elif rp >= 0.40:
            lines.append(f"- RANGE top-pred 精确率 {rp:.1%} 40-60% → **降权使用**（阈值放宽+人工复核）")
        else:
            lines.append(f"- RANGE top-pred 精确率 {rp:.1%} <40% → **门控存疑**，触发 RS012 §4 预案")
        out = GT_DIR / "confusion_report.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("->", out)
        return 0
    print("[empty] 预测文件无与 GT 匹配的样本（检查 datetime/symbol 格式）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
