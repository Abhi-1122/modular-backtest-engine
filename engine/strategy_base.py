"""
Strategy interface. Any strategy plugs into the engine by implementing
`on_tick`, which is called once per timestamp with the current market
snapshot and returns a list of desired Orders for that timestamp.

The engine (not the strategy) is responsible for:
  - iterating over time
  - applying fills to the Portfolio
  - computing and recording mark-to-market PnL
  - forcing end-of-day close

The strategy is only responsible for deciding WHAT to hold.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import pandas as pd

from .portfolio import Order


class MarketSnapshot:
    """Everything a strategy needs to know at a single timestamp."""

    def __init__(
        self,
        timestamp: pd.Timestamp,
        futures_price: Optional[float],
        option_prices: Dict[str, float],
        instruments_by_expiry: Dict[str, List[str]],
        nearest_expiry: Optional[str],
    ) -> None:
        self.timestamp = timestamp
        self.futures_price = futures_price
        self.option_prices = option_prices               # symbol -> last traded price up to `timestamp`
        self.instruments_by_expiry = instruments_by_expiry  # expiry -> list of symbols
        self.nearest_expiry = nearest_expiry


class Strategy(ABC):
    """Base class every strategy must implement."""

    @abstractmethod
    def on_tick(self, snapshot: MarketSnapshot, open_symbols: List[str]) -> List[Order]:
        """Return the list of orders to submit at this timestamp.

        `open_symbols` lists symbols currently held (quantity != 0), so the
        strategy can decide whether to rotate, hold, or exit.
        """
        raise NotImplementedError

    def on_day_start(self, date: str) -> None:
        """Optional hook, called once before each trading day starts."""
        pass

    def on_day_end(self, date: str) -> None:
        """Optional hook, called once after each trading day's forced close."""
        pass
