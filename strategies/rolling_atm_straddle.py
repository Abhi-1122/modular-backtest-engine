"""
Rolling ATM straddle strategy (the strategy described in the assignment).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from engine.instruments import parse_option_symbol
from engine.portfolio import Order, Side
from engine.strategy_base import MarketSnapshot, Strategy


class RollingATMStraddleStrategy(Strategy):
    def __init__(self, quantity_per_leg: int = 1) -> None:
        self.quantity_per_leg = quantity_per_leg
        self._current_strike: Optional[float] = None
        self._current_symbols: Dict[str, str] = {}

    def on_day_start(self, date: str) -> None:
        self._current_strike = None
        self._current_symbols = {}

    def _nearest_strike_symbols(self, snapshot: MarketSnapshot) -> Optional[Dict[str, str]]:
        if snapshot.futures_price is None or snapshot.nearest_expiry is None:
            return None
        symbols = snapshot.instruments_by_expiry.get(snapshot.nearest_expiry, [])
        if not symbols:
            return None

        strikes = {}
        for sym in symbols:
            inst = parse_option_symbol(sym)
            strikes.setdefault(inst.strike, {})[inst.opt_type] = sym

        complete_strikes = [k for k, v in strikes.items() if 'CE' in v and 'PE' in v]
        if not complete_strikes:
            return None

        nearest = min(complete_strikes, key=lambda k: abs(k - snapshot.futures_price))
        return {'strike': nearest, **strikes[nearest]}

    def on_tick(self, snapshot: MarketSnapshot, open_symbols: List[str]) -> List[Order]:
        target = self._nearest_strike_symbols(snapshot)
        if target is None:
            return []

        target_strike = target['strike']
        target_ce, target_pe = target['CE'], target['PE']
        currently_open = set(open_symbols)
        orders: List[Order] = []

        if self._current_strike is None:
            open_orders = self._open_pair(snapshot, target_ce, target_pe, currently_open)
            if len(open_orders) == 2:
                self._current_strike = target_strike
                self._current_symbols = {'CE': target_ce, 'PE': target_pe}
            return open_orders

        if target_strike != self._current_strike:
            old_ce = self._current_symbols.get('CE')
            old_pe = self._current_symbols.get('PE')
            orders += self._close_pair(snapshot, old_ce, old_pe, currently_open)
            currently_open = currently_open - {old_ce, old_pe}
            open_orders = self._open_pair(snapshot, target_ce, target_pe, currently_open)
            orders += open_orders
            if len(open_orders) == 2:
                self._current_strike = target_strike
                self._current_symbols = {'CE': target_ce, 'PE': target_pe}
            else:
                self._current_strike = None
                self._current_symbols = {}

        return orders

    def _open_pair(self, snapshot: MarketSnapshot, ce_symbol: str, pe_symbol: str, currently_open: set[str]) -> List[Order]:
        orders = []
        for symbol, reason in [(ce_symbol, 'entry_ce'), (pe_symbol, 'entry_pe')]:
            if symbol in currently_open:
                continue
            price = snapshot.option_prices.get(symbol)
            if price is None:
                continue
            orders.append(Order(
                timestamp=snapshot.timestamp,
                symbol=symbol,
                side=Side.BUY,
                quantity=self.quantity_per_leg,
                price=price,
                reason=reason,
            ))
        return orders

    def _close_pair(self, snapshot: MarketSnapshot, ce_symbol: Optional[str], pe_symbol: Optional[str], currently_open: set[str]) -> List[Order]:
        orders = []
        for symbol, reason in [(ce_symbol, 'rotate_exit_ce'), (pe_symbol, 'rotate_exit_pe')]:
            if symbol is None or symbol not in currently_open:
                continue
            price = snapshot.option_prices.get(symbol)
            if price is None:
                continue
            orders.append(Order(
                timestamp=snapshot.timestamp,
                symbol=symbol,
                side=Side.SELL,
                quantity=self.quantity_per_leg,
                price=price,
                reason=reason,
            ))
        return orders
