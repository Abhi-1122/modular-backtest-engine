"""
Order and position/PnL tracking primitives, independent of any strategy.

This version supports four fill types, not just long-only buy/sell-close:

    - BUY  on a flat or long position   -> opens/adds to a long position
    - SELL on a long position           -> closes/reduces a long position
    - SELL on a flat or short position  -> opens/adds to a short position
    - BUY  on a short position          -> closes/reduces a short position ("buy to cover")

This lets any strategy go long, short, or flip between the two using the
exact same Order/Side interface as before. Strategies that only ever buy
to open and sell to close (like the assignment's rolling straddle) are
completely unaffected by this change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import pandas as pd


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Order:
    timestamp: pd.Timestamp
    symbol: str
    side: Side
    quantity: int
    price: float               # fill price (backtest assumes fill at last traded price)
    reason: str = ""            # e.g. "entry", "rotate_exit", "rotate_entry", "eod_close"


@dataclass
class Position:
    symbol: str
    quantity: int = 0            # positive = long, negative = short, 0 = flat
    avg_price: float = 0.0

    def is_flat(self) -> bool:
        return self.quantity == 0

    def is_long(self) -> bool:
        return self.quantity > 0

    def is_short(self) -> bool:
        return self.quantity < 0


@dataclass
class TradeRecord:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    quantity: int
    direction: str               # "LONG" or "SHORT"
    realized_pnl: float
    reason: str = ""


class Portfolio:
    """Tracks open positions, realized PnL, and a full trade/order log.

    This class is strategy-agnostic: it only knows how to apply fills and
    compute PnL. Any strategy can drive it by submitting Orders, whether
    it trades long-only, short-only, or flips direction.
    """

    def __init__(self) -> None:
        self.positions: Dict[str, Position] = {}
        self.realized_pnl: float = 0.0
        self.trade_log: List[TradeRecord] = []
        self.order_log: List[Order] = []
        self._entry_time: Dict[str, pd.Timestamp] = {}

    def _get_or_create(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def apply_fill(self, order: Order) -> None:
        """Apply a fill. Supports opening/closing both long and short
        positions, and flipping direction in a single fill if the order
        quantity exceeds the current open quantity.
        """
        pos = self._get_or_create(order.symbol)
        signed_qty = order.quantity if order.side == Side.BUY else -order.quantity

        same_direction_or_flat = (
            pos.is_flat()
            or (pos.is_long() and order.side == Side.BUY)
            or (pos.is_short() and order.side == Side.SELL)
        )

        if same_direction_or_flat:
            # Opening a new position or adding to an existing one in the same direction.
            if pos.is_flat():
                self._entry_time[order.symbol] = order.timestamp
                pos.avg_price = order.price
            else:
                total_qty = abs(pos.quantity) + order.quantity
                pos.avg_price = (
                    (pos.avg_price * abs(pos.quantity)) + (order.price * order.quantity)
                ) / total_qty
            pos.quantity += signed_qty
            self.order_log.append(order)
            return

        # Opposite direction fill: this closes existing exposure, and may
        # flip into the opposite direction if order.quantity exceeds |pos.quantity|.
        closing_qty = min(abs(pos.quantity), order.quantity)
        direction = "LONG" if pos.is_long() else "SHORT"

        if direction == "LONG":
            pnl = (order.price - pos.avg_price) * closing_qty
        else:
            pnl = (pos.avg_price - order.price) * closing_qty

        self.realized_pnl += pnl
        self.trade_log.append(
            TradeRecord(
                symbol=order.symbol,
                entry_time=self._entry_time.get(order.symbol, order.timestamp),
                entry_price=pos.avg_price,
                exit_time=order.timestamp,
                exit_price=order.price,
                quantity=closing_qty,
                direction=direction,
                realized_pnl=pnl,
                reason=order.reason,
            )
        )

        remaining_order_qty = order.quantity - closing_qty
        pos.quantity += signed_qty * 1 if False else (
            # apply the closing portion first
            (-1 if direction == "LONG" else 1) * closing_qty
        )

        if remaining_order_qty > 0:
            # Flip: the fill overshoots the existing position, opening a
            # new position in the opposite direction with the leftover quantity.
            pos.avg_price = order.price
            pos.quantity = remaining_order_qty if order.side == Side.BUY else -remaining_order_qty
            self._entry_time[order.symbol] = order.timestamp
        elif pos.quantity == 0:
            pos.avg_price = 0.0
            self._entry_time.pop(order.symbol, None)

        self.order_log.append(order)

    def unrealized_pnl(self, last_prices: Dict[str, float]) -> float:
        total = 0.0
        for symbol, pos in self.positions.items():
            if pos.quantity == 0:
                continue
            price = last_prices.get(symbol)
            if price is None:
                continue
            total += (price - pos.avg_price) * pos.quantity
        return total

    def open_symbols(self) -> List[str]:
        return [s for s, p in self.positions.items() if not p.is_flat()]

    def total_pnl(self, last_prices: Dict[str, float]) -> float:
        return self.realized_pnl + self.unrealized_pnl(last_prices)