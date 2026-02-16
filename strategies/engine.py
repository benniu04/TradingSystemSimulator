import structlog

from core.event_bus import EventBus
from models import Event, EventType, Tick
from strategies.base import Strategy


class StrategyEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._strategies: list[Strategy] = []
        self._logger = structlog.get_logger(__name__)

    def register_strategy(self, strategy: Strategy) -> None:
        self._strategies.append(strategy)
        self._logger.info("strategy_registered", strategy_id=strategy.strategy_id)

    async def start(self) -> None:
        self._event_bus.subscribe(EventType.TICK, self._handle_tick)
        self._logger.info("strategy_engine_started", count=len(self._strategies))

    async def stop(self) -> None:
        self._event_bus.unsubscribe(EventType.TICK, self._handle_tick)
        self._logger.info("strategy_engine_stopped")

    async def _handle_tick(self, event: Event) -> None:
        tick = event.payload
        assert isinstance(tick, Tick)
        for strategy in self._strategies:
            if tick.symbol in strategy.symbols or not strategy.symbols:
                signal = await strategy.on_tick(tick)
                if signal is not None:
                    self._logger.info(
                        "signal_generated",
                        strategy=signal.strategy_id,
                        symbol=signal.symbol,
                        side=signal.side.value,
                        strength=signal.strength,
                    )
                    await self._event_bus.publish(
                        Event(type=EventType.SIGNAL, payload=signal)
                    )
