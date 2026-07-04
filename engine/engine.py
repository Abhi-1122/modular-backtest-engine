"""
The core backtest engine: strategy-agnostic event loop.

Design:
  - The engine drives time using the FUTURES ticks for the underlier
    (i.e. "every 1 sec" from the assignment = every futures tick).
  - Option prices are tracked via a last-known-price cache that is updated
    from option tick data as time advances, so the strategy always sees
    the most recent observed price at or before the current timestamp.
  - The strategy is only asked "what should I hold right now" via
    `on_tick`; the engine applies the resulting orders to the Portfolio
    and records mark-to-market PnL at every futures timestamp.
  - At the end of each day, the engine force-closes any open positions
    at their last known price, regardless of what the strategy wants.

This allows a different strategy to be plugged in without touching this file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .data_loader import DayData, list_trading_dates, load_day
from .instruments import OptionInstrument
from .portfolio import Order, Portfolio, Side
from .strategy_base import MarketSnapshot, Strategy


@dataclass
class BacktestConfig:
    all_data_dir: str
    underliers: List[str]
    quantity_per_leg: int = 1


@dataclass
class BacktestResult:
    mtm_series: pd.DataFrame        # columns: timestamp, underlier, realized_pnl, unrealized_pnl, total_pnl
    trade_log: pd.DataFrame         # one row per closed trade
    order_log: pd.DataFrame         # one row per order/fill
    position_timeline: pd.DataFrame # columns: timestamp, underlier, open_symbols (comma joined)


def _nearest_expiry_for_day(instruments: Dict[str, OptionInstrument], underlier: str, date: str) -> Optional[str]:
    """Pick the expiry (>= current date) closest to the current date, among
    instruments available for this underlier on this day.
    """
    expiries = sorted({
        inst.expiry for inst in instruments.values()
        if inst.underlier == underlier
    })
    if not expiries:
        return None
    # Expiries are YYMMDD strings; compare lexically against date's YYMMDD suffix.
    date_yy = date[2:]  # "20221101" -> "221101"
    future_expiries = [e for e in expiries if e >= date_yy]
    return min(future_expiries) if future_expiries else min(expiries)


def _symbols_for_expiry(instruments: Dict[str, OptionInstrument], underlier: str, expiry: str) -> Dict[str, OptionInstrument]:
    return {
        sym: inst for sym, inst in instruments.items()
        if inst.underlier == underlier and inst.expiry == expiry
    }


class BacktestEngine:
    """Strategy-agnostic backtest engine.

    Usage:
        engine = BacktestEngine(config)
        result = engine.run(strategy)
    """

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def run(self, strategy: Strategy) -> Dict[str, BacktestResult]:
        """Run the strategy across all trading days, separately per underlier.

        Returns a dict: underlier -> BacktestResult
        """
        dates = list_trading_dates(self.config.all_data_dir)
        portfolios = {u: Portfolio() for u in self.config.underliers}
        mtm_rows: Dict[str, List[dict]] = {u: [] for u in self.config.underliers}
        position_rows: Dict[str, List[dict]] = {u: [] for u in self.config.underliers}

        for date in dates:
            day = load_day(self.config.all_data_dir, date, self.config.underliers)
            strategy.on_day_start(date)

            for underlier in self.config.underliers:
                self._run_day_for_underlier(
                    day, underlier, strategy, portfolios[underlier],
                    mtm_rows[underlier], position_rows[underlier],
                )

            strategy.on_day_end(date)

        results: Dict[str, BacktestResult] = {}
        for underlier in self.config.underliers:
            portfolio = portfolios[underlier]
            results[underlier] = BacktestResult(
                mtm_series=pd.DataFrame(mtm_rows[underlier]),
                trade_log=pd.DataFrame([t.__dict__ for t in portfolio.trade_log]),
                order_log=pd.DataFrame([
                    {**o.__dict__, "side": o.side.value} for o in portfolio.order_log
                ]),
                position_timeline=pd.DataFrame(position_rows[underlier]),
            )
        return results

    def _run_day_for_underlier(
        self,
        day: DayData,
        underlier: str,
        strategy: Strategy,
        portfolio: Portfolio,
        mtm_rows: List[dict],
        position_rows: List[dict],
    ) -> None:
        futures_df = day.futures.get(underlier)
        if futures_df is None or futures_df.empty:
            return

        nearest_expiry = _nearest_expiry_for_day(day.instruments, underlier, day.date)
        expiry_symbols = _symbols_for_expiry(day.instruments, underlier, nearest_expiry) if nearest_expiry else {}

        # Last known price cache, updated as we scan forward in time.
        last_option_price: Dict[str, float] = {}
        option_iters = {
            sym: iter(day.options[sym].itertuples())
            for sym in expiry_symbols
        }
        option_peek: Dict[str, Optional[tuple]] = {sym: next(it, None) for sym, it in option_iters.items()}

        instruments_by_expiry: Dict[str, List[str]] = {}
        for sym, inst in expiry_symbols.items():
            instruments_by_expiry.setdefault(inst.expiry, []).append(sym)

        for row in futures_df.itertuples():
            timestamp = row.Index
            futures_price = row.Price

            # Advance option price cache to include all ticks at or before this timestamp.
            for sym in list(option_peek.keys()):
                peek = option_peek[sym]
                while peek is not None and peek.Index <= timestamp:
                    last_option_price[sym] = peek.Price
                    peek = next(option_iters[sym], None)
                option_peek[sym] = peek

            snapshot = MarketSnapshot(
                timestamp=timestamp,
                futures_price=futures_price,
                option_prices=dict(last_option_price),
                instruments_by_expiry=instruments_by_expiry,
                nearest_expiry=nearest_expiry,
            )

            open_symbols = portfolio.open_symbols()
            orders = strategy.on_tick(snapshot, open_symbols)
            for order in orders:
                portfolio.apply_fill(order)

            realized = portfolio.realized_pnl
            unrealized = portfolio.unrealized_pnl(last_option_price)
            mtm_rows.append({
                "timestamp": timestamp,
                "underlier": underlier,
                "realized_pnl": realized,
                "unrealized_pnl": unrealized,
                "total_pnl": realized + unrealized,
            })
            position_rows.append({
                "timestamp": timestamp,
                "underlier": underlier,
                "open_symbols": ",".join(portfolio.open_symbols()),
            })

        # Force close any open positions at end of day, at last known price.
        # Works for both long and short positions: a long is closed by
        # selling, a short is closed by buying back.
        last_timestamp = futures_df.index[-1]
        for symbol in portfolio.open_symbols():
            price = last_option_price.get(symbol)
            if price is None:
                continue
            pos = portfolio.positions[symbol]
            close_side = Side.SELL if pos.quantity > 0 else Side.BUY
            portfolio.apply_fill(
                Order(
                    timestamp=last_timestamp,
                    symbol=symbol,
                    side=close_side,
                    quantity=abs(pos.quantity),
                    price=price,
                    reason="eod_close",
                )
            )

        realized = portfolio.realized_pnl
        unrealized = portfolio.unrealized_pnl(last_option_price)
        mtm_rows.append({
            "timestamp": last_timestamp,
            "underlier": underlier,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": realized + unrealized,
        })
        position_rows.append({
            "timestamp": last_timestamp,
            "underlier": underlier,
            "open_symbols": "",
        })
