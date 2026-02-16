import abc

import structlog

from models import Signal, Tick


class Strategy(abc.ABC):
    def __init__(self, strategy_id: str, symbols: list[str]) -> None:
        self.strategy_id = strategy_id
        self.symbols = symbols
        self._logger = structlog.get_logger(self.__class__.__name__)

    @abc.abstractmethod
    async def on_tick(self, tick: Tick) -> Signal | None:
        """Process a tick; return a Signal if the strategy wants to trade."""
        ...

    @abc.abstractmethod
    def reset(self) -> None:
        """Reset internal state."""
        ...
