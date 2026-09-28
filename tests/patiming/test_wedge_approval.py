from datetime import timedelta
from types import SimpleNamespace

from conftest import BASE, make_bar, make_engine, submit_ok
from vnpy_patiming.config import build_config
from vnpy_patiming.signals import SignalContext
from vnpy_patiming.signals.detectors import WedgeThreePushDetector
from vnpy_patiming.structures import LevelManager, Pivot, PivotDetector


def test_wedge_short_detector(tmp_path, clock):
    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2})
    seq = [103.0, 104.2, 103.6, 104.4, 103.8, 104.6, 103.9, 104.1, 103.8,
           103.6]
    bars = [make_bar(BASE + timedelta(minutes=i), c - 0.05, c + 0.3, c - 0.3, c)
            for i, c in enumerate(seq)]
    pivots = PivotDetector(2)
    pivots.confirmed = [
        Pivot("L", 102.7, bars[0].datetime, bars[2].datetime),
        Pivot("H", 104.2, bars[1].datetime, bars[3].datetime),
        Pivot("L", 103.3, bars[2].datetime, bars[4].datetime),
        Pivot("H", 104.4, bars[3].datetime, bars[5].datetime),
        Pivot("L", 103.5, bars[4].datetime, bars[6].datetime),
        Pivot("H", 104.3, bars[5].datetime, bars[7].datetime),
    ]
    ema = SimpleNamespace(value=None, slope=lambda lookback=5: 0.0)
    ctx = SignalContext(bars=bars, atr=1.0, ema=ema, pivots=pivots,
                        levels=LevelManager(), cfg=cfg, direction="both",
                        context_tag="reversal", now=bars[-1].datetime,
                        price_tick=0.2, fake_log=[])
    drafts = WedgeThreePushDetector().detect(ctx)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "short" and d.signal_id == "WEDGE_THREE_PUSH"
    assert d.trigger["level"] == 102.9  # last low 103.3 - 2 ticks * 0.2
    assert d.stop["level"] == 104.55  # h3 104.3 + 0.25 ATR
    assert d.invalidation == {"type": "close_above", "level": 104.3}


def test_llm_require_approval_flow(tmp_path, clock):
    eng = make_engine(tmp_path, clock, require_approval=True)
    payload = {"symbol": "rb2501.SHFE", "selection_timeframe": "1m",
               "exec_timeframe": "1m", "context_tag": "breakout",
               "reason_code": "BREAKOUT_WATCH", "reason_note": "需要审批"}
    r = eng.submit_instruction("llm:s1",
                               {**payload, "instruction_id": "P-1",
                                "producer_revision": 1})
    assert r["ok"] and r["status"] == "PENDING_APPROVAL"
    eng.reconcile()
    assert ("rb2501.SHFE", "1m") not in eng.tasks  # 未审批不监控

    out = eng.approve_instruction("llm:s1", "P-1")
    assert out["ok"] and out["status"] == "ACTIVE"
    eng.reconcile()
    assert ("rb2501.SHFE", "1m") in eng.tasks

    r2 = eng.submit_instruction("llm:s1",
                                {**payload, "instruction_id": "P-2",
                                 "producer_revision": 1})
    assert r2["ok"] and r2["status"] == "PENDING_APPROVAL"
    out = eng.reject_instruction("llm:s1", "P-2")
    assert out["ok"] and out["status"] == "REVOKED"


def test_reconcile_rejects_pending_revoke(tmp_path, clock):
    eng = make_engine(tmp_path, clock, require_approval=True)
    result = eng.submit_instruction("llm:s1", {
        "instruction_id": "P-REJECT",
        "producer_revision": 1,
        "symbol": "rb2501.SHFE",
        "selection_timeframe": "1m",
        "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH",
        "reason_note": "pending revoke",
    })
    assert result["ok"] and result["status"] == "PENDING_APPROVAL"
    revoked = eng.revoke("llm:s1", "P-REJECT", 2)
    assert revoked["ok"]
    eng.reconcile()
    row = eng.db.fetch_instruction("llm:s1", "P-REJECT")
    assert row["status"] == "REVOKED"
