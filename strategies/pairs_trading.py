import statistics
from collections import deque
from models import Side, Signal, Tick
from strategies.base import Strategy

class PairsTradingStrategy(Strategy):
    def __init__(
        self,
        strategy_id: str = "pairs",
        symbol_a: str = "AAPL",
        symbol_b: str = "MSFT",
        window_size: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
    ) -> None:
        # Register both symbols
        super().__init__(strategy_id, [symbol_a, symbol_b])
        self._symbol_a = symbol_a
        self._symbol_b = symbol_b
        self._window_size = window_size
        self._entry_z = entry_z
        self._exit_z = exit_z
        self._prices_a: deque[float] = deque(maxlen=window_size)
        self._prices_b: deque[float] = deque(maxlen=window_size)
        self._latest: dict[str, float] = {}
        self._trade_state: int = 0  # 0=flat, 1=long A/short B, -1=short A/long B
    
    async def on_tick(self, tick: Tick) -> Signal | list[Signal] | None:
        symbol = tick.symbol
        price = float(tick.price)
        self._latest[symbol] = price
        
        if symbol == self._symbol_a:
            self._prices_a.append(price)
        elif symbol == self._symbol_b:
            self._prices_b.append(price)
        else:
            return None

        # Need full windows for both
        if (len(self._prices_a) < self._window_size
            or len(self._prices_b) < self._window_size):
            return None
        
        # Need a recent price for both
        if self._symbol_a not in self._latest or self._symbol_b not in self._latest:
            return None

        # Compute the price ratio and its z-score
        ratios = [
            a / b
            for a, b in zip(self._prices_a, self._prices_b)
        ]
        mean_ratio = statistics.mean(ratios)
        std_ratio = statistics.stdev(ratios)
        if std_ratio == 0:
            return None
        
        current_ratio = self._latest[self._symbol_a] / self._latest[self._symbol_b]
        z = (current_ratio - mean_ratio) / std_ratio
        
        # Exit: spread has converged
        if self._trade_state != 0 and abs(z) < self._exit_z:
            signals = self._close_signals(abs(z))
            self._trade_state = 0
            return signals
        
        # Entry: spread has diverged
        if self._trade_state == 0:
            if z > self._entry_z:
                # A is expensive relative to B -> short A, long B
                self._trade_state = -1
                strength = min(abs(z) / (self._entry_z * 2), 1.0)
                return [
                    Signal(
                        strategy_id=self.strategy_id,
                        symbol=self._symbol_a,
                        side=Side.SELL,
                        strength=strength,
                    ),
                    Signal(
                        strategy_id=self.strategy_id,
                        symbol=self._symbol_b,
                        side=Side.BUY,
                        strength = strength
                    )
                ] 
            elif z < -self._entry_z:
                # B is expensive relative to A -> long A, short B
                self._trade_state = 1
                strength = min(abs(z) / (self._entry_z * 2), 1.0)
                return [
                    Signal(
                        strategy_id=self.strategy_id,
                        symbol=self._symbol_a,
                        side=Side.BUY,
                        strength=strength
                    ),
                    Signal(
                        strategy_id=self.strategy_id,
                        symbol=self._symbol_b,
                        side=Side.SELL,
                        strength=strength
                    )
                ]
        
        return None

    def _close_signals(self, strength: float) -> list[Signal]:
        """Generate signals to close the current pair position."""
        if self._trade_state == 1:
            # Was long A / short B -> sell A, buy B
            return [
                Signal(
                    strategy_id=self.strategy_id,
                    symbol=self._symbol_a,
                    side=Side.SELL,
                    strength=strength
                ),
                Signal(
                    strategy_id=self.strategy_id,
                    symbol=self._symbol_b,
                    side=Side.BUY,
                    strength=strength
                ),
            ]
        else:
            # Was short A / long B -> buy A, sell B
            return [
                Signal(
                    strategy_id=self.strategy_id,
                    symbol=self._symbol_a,
                    side=Side.BUY,
                    strength=strength
                ),
                Signal(
                    strategy_id=self.strategy_id,
                    symbol=self._symbol_b,
                    side=Side.SELL,
                    strength=strength
                ),
            ]
    
    def reset(self) -> None:
        self._prices_a.clear()
        self._prices_b.clear()
        self._latest.clear()
        self._trade_state = 0
        