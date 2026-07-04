"""
Rolling ATM straddle strategy (the strategy described in the assignment).

Rules implemented:
- Trade only the nearest expiry provided by the engine.
- At each futures timestamp, find the strike closest to futures price.
- Hold exactly one CE + one PE for that strike.
- If the closest strike changes, rotate at the SAME timestamp:
    1) sell old CE/PE
    2) buy new CE/PE
- If the new target pair is not fully tradable (missing CE/PE price),
  keep holding the current pair and do nothing.
- Use the actual open portfolio symbols passed by the engine as the
  source of truth.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from engine.instruments import parse_option_symbol
from engine.portfolio import Order, Side
from engine.strategy_base import MarketSnapshot, Strategy


class RollingATMStraddleStrategy(Strategy):
    def __init__(self, quantity_per_leg: int = 1) -> None:
        self.quantity_per_leg = quantity_per_leg

    def on_day_start(self, date: str) -> None:
        pass

    def _nearest_strike_symbols(self, snapshot: MarketSnapshot) -> Optional[Dict[str, object]]:
        if snapshot.futures_price is None or snapshot.nearest_expiry is None:
            return None

        symbols = snapshot.instruments_by_expiry.get(snapshot.nearest_expiry, [])
        if not symbols:
            return None

        strikes: Dict[int, Dict[str, str]] = {}
        for sym in symbols:
            inst = parse_option_symbol(sym)
            strikes.setdefault(inst.strike, {})[inst.opt_type] = sym

        complete_strikes = [
            strike for strike, legs in strikes.items()
            if "CE" in legs and "PE" in legs
        ]
        if not complete_strikes:
            return None

        nearest = min(
            complete_strikes,
            key=lambda strike: abs(strike - snapshot.futures_price)
        )

        return {
            "strike": nearest,
            "CE": strikes[nearest]["CE"],
            "PE": strikes[nearest]["PE"],
        }

    def _extract_current_pair(self, open_symbols: List[str]) -> Set[str]:
        return set(open_symbols)

    def on_tick(self, snapshot: MarketSnapshot, open_symbols: List[str]) -> List[Order]:
        target = self._nearest_strike_symbols(snapshot)
        if target is None:
            return []

        target_ce = target["CE"]
        target_pe = target["PE"]
        target_set = {target_ce, target_pe}

        current_open = self._extract_current_pair(open_symbols)
        orders: List[Order] = []

        # Already holding exactly the desired pair.
        if current_open == target_set:
            return []

        # If nothing is open, open the target pair only if both prices exist.
        if not current_open:
            ce_price = snapshot.option_prices.get(target_ce)
            pe_price = snapshot.option_prices.get(target_pe)

            if ce_price is None or pe_price is None:
                return []

            return [
                Order(
                    timestamp=snapshot.timestamp,
                    symbol=target_ce,
                    side=Side.BUY,
                    quantity=self.quantity_per_leg,
                    price=ce_price,
                    reason="entry_ce",
                ),
                Order(
                    timestamp=snapshot.timestamp,
                    symbol=target_pe,
                    side=Side.BUY,
                    quantity=self.quantity_per_leg,
                    price=pe_price,
                    reason="entry_pe",
                ),
            ]

        # We are holding something, and target differs.
        # To rotate at the SAME timestamp safely, require all needed prices:
        # - prices for everything currently open (to close)
        # - prices for both target legs (to open)
        required_symbols = set(current_open) | target_set
        for symbol in required_symbols:
            if snapshot.option_prices.get(symbol) is None:
                return []

        # Close anything not in target first.
        for symbol in sorted(current_open - target_set):
            orders.append(Order(
                timestamp=snapshot.timestamp,
                symbol=symbol,
                side=Side.SELL,
                quantity=self.quantity_per_leg,
                price=snapshot.option_prices[symbol],
                reason="rotate_exit",
            ))

        # Then open anything missing from target.
        for symbol in [target_ce, target_pe]:
            if symbol not in current_open:
                orders.append(Order(
                    timestamp=snapshot.timestamp,
                    symbol=symbol,
                    side=Side.BUY,
                    quantity=self.quantity_per_leg,
                    price=snapshot.option_prices[symbol],
                    reason="rotate_entry",
                ))

        return orders