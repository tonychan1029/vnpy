"""vnpy MainEngine adapter: tick -> 1m bars -> engine (App form)."""

from __future__ import annotations

from pathlib import Path

from vnpy.event import EventEngine
from vnpy.trader.app import BaseApp
from vnpy.trader.constant import Interval
from vnpy.trader.engine import MainEngine
from vnpy.trader.event import EVENT_TICK
from vnpy.trader.object import TickData
from vnpy.trader.utility import BarGenerator

from .engine import PatimingEngine


class VnPatimingEngine(PatimingEngine):
    """PatimingEngine wired into MainEngine event flow."""

    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        engine_name: str,
        db_path: str | None = None,
        cfg_overrides: dict | None = None,
        data_mode: str = "ctp_tick",
    ) -> None:
        super().__init__(
            db_path or str(Path.home() / ".vnpatiming" / "patiming.db"),
            cfg_overrides,
            data_mode=data_mode,
        )
        self.main_engine = main_engine
        self.event_engine = event_engine
        self.engine_name = engine_name
        self._bgs: dict[str, BarGenerator] = {}
        main_engine.register_event(EVENT_TICK, self._on_tick_event)

    def _on_tick_event(self, event) -> None:
        tick: TickData = event.data
        bg = self._bgs.get(tick.vt_symbol)
        if bg is None:
            bg = BarGenerator(tick.symbol, Interval.MINUTE, self.on_1m_bar)
            self._bgs[tick.vt_symbol] = bg
        bg.update_tick(tick)
        self.on_tick(tick)

    def subscribe(self, symbol: str, exchange) -> None:
        from vnpy.trader.object import SubscribeRequest

        req = SubscribeRequest(symbol=symbol.split(".")[0], exchange=exchange)
        self.main_engine.subscribe(req, symbol.split(".")[1])

    def close(self) -> None:
        self.stop()
        self.db.close()


class PatimingApp(BaseApp):
    app_name = "PatimingEngine"
    app_module = "vnpy_patiming.app"
    app_path = Path(__file__).parent
    display_name = "PA择时引擎"
    engine_class = VnPatimingEngine
    widget_name = ""
    icon_name = ""
