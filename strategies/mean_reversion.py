import statistics
from collections import deque

from models import Side, Signal, Tick
from strategies.base import Strategy


class MeanReversionStrategy(Strategy):
    def __init__(
        self,
        strategy_id: str = "mean_reversion",
        symbols: list[str] | None = None,
        window_size: int = 50,
        entry_z: float = 2.0,
    ) -> None:
        super().__init__(strategy_id, symbols or [])
        self._window_size = window_size
        self._entry_z = entry_z
        self._price_windows: dict[str, deque[float]] = {}

    async def on_tick(self, tick: Tick) -> Signal | None:
        symbol = tick.symbol
        if symbol not in self._price_windows:
            self._price_windows[symbol] = deque(maxlen=self._window_size)

        window = self._price_windows[symbol]
        price = float(tick.price)
        window.append(price)

        if len(window) < self._window_size:
            return None

        mean = statistics.mean(window)
        stdev = statistics.stdev(window)
        if stdev == 0:
            return None

        z_score = (price - mean) / stdev

        if z_score > self._entry_z:
            return Signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side=Side.SELL,
                strength=min(abs(z_score) / (self._entry_z * 2), 1.0),
            )
        elif z_score < -self._entry_z:
            return Signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                side=Side.BUY,
                strength=min(abs(z_score) / (self._entry_z * 2), 1.0),
            )
        return None

    def reset(self) -> None:
        self._price_windows.clear()
