"""
Entry point: run the rolling ATM straddle backtest across all days for
NIFTY and BANKNIFTY, and write out results CSVs.

Usage:
    python run_backtest.py --data-dir /path/to/allData --out-dir results
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from engine.engine import BacktestConfig, BacktestEngine
from strategies.rolling_atm_straddle import RollingATMStraddleStrategy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Path to allData/ directory")
    parser.add_argument("--out-dir", default="results", help="Directory to write result CSVs")
    parser.add_argument("--underliers", nargs="+", default=["NIFTY", "BANKNIFTY"])
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    all_mtm = []
    all_trades = []
    all_orders = []
    all_positions = []

    for underlier in args.underliers:
        engine = BacktestEngine(BacktestConfig(all_data_dir=args.data_dir, underliers=[underlier]))
        strategy = RollingATMStraddleStrategy(quantity_per_leg=1)
        result = engine.run(strategy)[underlier]

        result.mtm_series.to_csv(os.path.join(args.out_dir, f"{underlier}_mtm.csv"), index=False)
        result.trade_log.to_csv(os.path.join(args.out_dir, f"{underlier}_trades.csv"), index=False)
        result.order_log.to_csv(os.path.join(args.out_dir, f"{underlier}_orders.csv"), index=False)
        result.position_timeline.to_csv(os.path.join(args.out_dir, f"{underlier}_positions.csv"), index=False)

        all_mtm.append(result.mtm_series)
        all_trades.append(result.trade_log)
        all_orders.append(result.order_log)
        all_positions.append(result.position_timeline)

        total_pnl = result.mtm_series["total_pnl"].iloc[-1] if not result.mtm_series.empty else 0.0
        n_trades = len(result.trade_log)
        print(f"{underlier}: total_pnl={total_pnl:.2f}, closed_trades={n_trades}")

    pd.concat(all_mtm, ignore_index=True).to_csv(os.path.join(args.out_dir, "combined_mtm.csv"), index=False)
    pd.concat(all_trades, ignore_index=True).to_csv(os.path.join(args.out_dir, "combined_trades.csv"), index=False)


if __name__ == "__main__":
    main()
