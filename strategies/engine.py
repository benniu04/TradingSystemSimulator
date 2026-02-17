import structlog
from core.event_bus import EventBus
from models import Event, EventType, Tick, Signal
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
            if not self._strategy_wants_symbol(strategy, tick.symbol):
                continue

            try:
                result = await strategy.on_tick(tick)
            except Exception:
                self._logger.exception(
                    "strategy_error",
                    strategy_id=strategy.strategy_id,
                    symbol=tick.symbol,
                )
                continue

            if result is None:
                continue

            # Normalize to list so pairs trading (list[Signal])
            # and single strategies (Signal) both work
            signals = result if isinstance(result, list) else [result]

            for signal in signals:
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

    @staticmethod
    def _strategy_wants_symbol(strategy: Strategy, symbol: str) -> bool:
        # Empty symbols list means the strategy wants everything
        return not strategy.symbols or symbol in strategy.symbols