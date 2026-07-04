"""
Sanity / correctness tests for the backtest engine.

These are not exhaustive unit tests; they are targeted checks on the
parts of the system most likely to be wrong: filename parsing, nearest
strike selection, and PnL arithmetic on a fully hand-computable scenario.

Run with: python -m pytest tests/ -v
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.instruments import parse_option_symbol
from engine.portfolio import Order, Portfolio, Side
from engine.data_loader import list_trading_dates
from engine.engine import BacktestConfig, BacktestEngine
from strategies.rolling_atm_straddle import RollingATMStraddleStrategy


def test_parse_option_symbol_basic():
    inst = parse_option_symbol("NIFTY22110314550PE")
    assert inst.underlier == "NIFTY"
    assert inst.expiry == "221103"
    assert inst.strike == 14550.0
    assert inst.opt_type == "PE"


def test_parse_option_symbol_banknifty():
    inst = parse_option_symbol("BANKNIFTY22112443200CE")
    assert inst.underlier == "BANKNIFTY"
    assert inst.expiry == "221124"
    assert inst.strike == 43200.0
    assert inst.opt_type == "CE"


def test_parse_option_symbol_invalid_raises():
    with pytest.raises(ValueError):
        parse_option_symbol("NOT_A_VALID_SYMBOL")


def test_portfolio_realized_pnl_matches_hand_calculation():
    """Reproduces the worked example from the assignment writeup:
    buy 20000CE@100, sell@85 -> -15
    buy 20000PE@95,  sell@120 -> +25
    Expected total realized PnL = 10
    """
    portfolio = Portfolio()
    t0 = pd.Timestamp("2022-11-01 09:30:00")
    t1 = pd.Timestamp("2022-11-01 09:30:10")

    portfolio.apply_fill(Order(t0, "20000CE", Side.BUY, 1, 100.0, "entry"))
    portfolio.apply_fill(Order(t0, "20000PE", Side.BUY, 1, 95.0, "entry"))

    portfolio.apply_fill(Order(t1, "20000CE", Side.SELL, 1, 85.0, "rotate_exit"))
    portfolio.apply_fill(Order(t1, "20000PE", Side.SELL, 1, 120.0, "rotate_exit"))

    assert portfolio.realized_pnl == pytest.approx(10.0)
    assert len(portfolio.trade_log) == 2
    assert portfolio.open_symbols() == []


def test_portfolio_unrealized_pnl_before_close():
    portfolio = Portfolio()
    t0 = pd.Timestamp("2022-11-01 09:30:00")
    portfolio.apply_fill(Order(t0, "20000CE", Side.BUY, 1, 100.0, "entry"))
    portfolio.apply_fill(Order(t0, "20000PE", Side.BUY, 1, 95.0, "entry"))

    # Market moves: CE now worth 108, PE now worth 90 (matches earlier writeup example)
    unrealized = portfolio.unrealized_pnl({"20000CE": 108.0, "20000PE": 90.0})
    assert unrealized == pytest.approx(3.0)  # (108-100) + (90-95) = 8 - 5 = 3


def test_portfolio_averages_in_when_buying_more_of_same_direction():
    """The Portfolio itself does not enforce a max-position-of-1 cap; it
    correctly averages price when adding to an existing long position.
    Enforcing "max position = 1" is the strategy's responsibility (it
    must not submit a second BUY on an already-open symbol), not the
    Portfolio's. This test documents and checks the Portfolio's actual
    behavior after the long/short generalization.
    """
    portfolio = Portfolio()
    t0 = pd.Timestamp("2022-11-01 09:30:00")
    portfolio.apply_fill(Order(t0, "20000CE", Side.BUY, 1, 100.0, "entry"))
    portfolio.apply_fill(Order(t0, "20000CE", Side.BUY, 1, 105.0, "double_entry"))

    pos = portfolio.positions["20000CE"]
    assert pos.quantity == 2
    assert pos.avg_price == pytest.approx(102.5)


def test_strategy_never_issues_a_second_buy_on_already_open_symbol():
    """This is where the max-position-of-1 rule is actually enforced: at
    the strategy level. The rolling ATM straddle strategy must never try
    to open a symbol that is already in open_symbols.
    """
    from strategies.rolling_atm_straddle import RollingATMStraddleStrategy
    from engine.strategy_base import MarketSnapshot

    strategy = RollingATMStraddleStrategy(quantity_per_leg=1)
    strategy.on_day_start("20221101")

    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2022-11-01 09:30:00"),
        futures_price=20000.0,
        option_prices={"NIFTY22110320000CE": 100.0, "NIFTY22110320000PE": 95.0},
        instruments_by_expiry={"221103": ["NIFTY22110320000CE", "NIFTY22110320000PE"]},
        nearest_expiry="221103",
    )

    orders_first = strategy.on_tick(snapshot, open_symbols=[])
    assert len(orders_first) == 2

    # Same snapshot again, strategy already holds the pair -> must submit no new BUYs.
    open_symbols = [o.symbol for o in orders_first]
    orders_second = strategy.on_tick(snapshot, open_symbols=open_symbols)
    assert orders_second == []


def test_engine_runs_end_to_end_on_sample_data():
    """Smoke test on a small real-data subset.

    Instead of traversing the entire dataset, use only the first available
    trading day and one underlier at a time. This keeps the test fast while
    still exercising the real data-loading path.
    """
    data_dir = os.path.expanduser("./allData")
    if not os.path.isdir(data_dir):
        pytest.skip("Sample data not present in this environment")

    from engine.data_loader import list_trading_dates
    from engine.engine import BacktestConfig, BacktestEngine
    from strategies.rolling_atm_straddle import RollingATMStraddleStrategy

    dates = list_trading_dates(data_dir)
    if not dates:
        pytest.skip("No trading dates found in dataset")

    first_date = dates[0]

    # Build a tiny temporary subset containing only one date.
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(data_dir, f"NSE_{first_date}")
        dst_root = os.path.join(tmpdir, "allData")
        os.makedirs(dst_root, exist_ok=True)
        shutil.copytree(src, os.path.join(dst_root, f"NSE_{first_date}"))

        for underlier in ["NIFTY", "BANKNIFTY"]:
            config = BacktestConfig(all_data_dir=dst_root, underliers=[underlier])
            engine = BacktestEngine(config)
            strategy = RollingATMStraddleStrategy(quantity_per_leg=1)
            result = engine.run(strategy)[underlier]

            # If this underlier is absent on that day, skip silently.
            if result.mtm_series.empty:
                continue

            assert not result.position_timeline.empty

            # End of day should always be flat.
            last_positions = result.position_timeline["open_symbols"].iloc[-1]
            assert last_positions == ""

            # PnL column should be finite.
            assert result.mtm_series["total_pnl"].notna().all()


def test_strategy_never_holds_more_than_one_pair_at_a_time():
    """Structural test on a small real-data subset.

    Uses only the first available trading day and only NIFTY, which is
    enough to verify the strategy never holds more than one CE+PE pair.
    """
    data_dir = os.path.expanduser("./allData")
    if not os.path.isdir(data_dir):
        pytest.skip("Sample data not present in this environment")

    from engine.data_loader import list_trading_dates
    from engine.engine import BacktestConfig, BacktestEngine
    from strategies.rolling_atm_straddle import RollingATMStraddleStrategy

    dates = list_trading_dates(data_dir)
    if not dates:
        pytest.skip("No trading dates found in dataset")

    first_date = dates[0]

    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(data_dir, f"NSE_{first_date}")
        dst_root = os.path.join(tmpdir, "allData")
        os.makedirs(dst_root, exist_ok=True)
        shutil.copytree(src, os.path.join(dst_root, f"NSE_{first_date}"))

        config = BacktestConfig(all_data_dir=dst_root, underliers=["NIFTY"])
        engine = BacktestEngine(config)
        strategy = RollingATMStraddleStrategy(quantity_per_leg=1)
        result = engine.run(strategy)["NIFTY"]

        if result.position_timeline.empty:
            pytest.skip("NIFTY data not present on selected test day")

        max_open = result.position_timeline["open_symbols"].apply(
            lambda s: 0 if s == "" else len(s.split(","))
        ).max()
        assert max_open <= 2
