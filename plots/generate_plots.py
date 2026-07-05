"""
Generate only the assignment-relevant backtest plots.

Expected input files in results/:
    NIFTY_mtm.csv
    NIFTY_trades.csv
    NIFTY_positions.csv
    BANKNIFTY_mtm.csv
    BANKNIFTY_trades.csv
    BANKNIFTY_positions.csv

Output:
    PNG plots saved under plots/

Plots generated for each underlier:
    1. Total PnL over time
    2. Daily PnL
    3. Drawdown
    4. Open position count over time
    5. Trade PnL distribution

Usage:
    python3.12 generate_plots.py --results-dir ../results --plots-dir ./
"""

from __future__ import annotations

import argparse
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_csv(path: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    return df


def prepare_mtm(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out


def prepare_positions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out = out.sort_values("timestamp").reset_index(drop=True)
    out["open_count"] = out["open_symbols"].fillna("").apply(
        lambda s: 0 if str(s).strip() == "" else len(str(s).split(","))
    )
    return out


def compute_drawdown(total_pnl: pd.Series) -> pd.Series:
    running_peak = total_pnl.cummax()
    return total_pnl - running_peak


def save_figure(fig: go.Figure, path: str, width: int = 1200, height: int = 700) -> None:
    fig.update_layout(
        template="plotly_white",
        width=width,
        height=height,
        title_x=0.5,
        font=dict(size=14),
        margin=dict(l=60, r=40, t=80, b=60),
    )
    fig.write_image(path)


def underlier_plot_path(plots_dir: str, underlier: str, filename: str) -> str:
    out_dir = os.path.join(plots_dir, underlier)
    ensure_dir(out_dir)
    return os.path.join(out_dir, filename)


def plot_total_pnl(mtm: pd.DataFrame, underlier: str, plots_dir: str) -> None:
    fig = px.line(
        mtm,
        x="timestamp",
        y="total_pnl",
        title=f"{underlier} Total PnL Over Time",
        labels={"timestamp": "Timestamp", "total_pnl": "Total PnL"},
    )
    save_figure(fig, underlier_plot_path(plots_dir, underlier, "total_pnl.png"))


def plot_daily_pnl(mtm: pd.DataFrame, underlier: str, plots_dir: str) -> None:
    daily = mtm.copy()
    daily["date"] = daily["timestamp"].dt.date
    daily = (
        daily.groupby("date", as_index=False)["total_pnl"]
        .last()
        .rename(columns={"total_pnl": "day_end_total_pnl"})
    )

    daily["daily_pnl"] = daily["day_end_total_pnl"].diff().fillna(daily["day_end_total_pnl"])

    fig = px.bar(
        daily,
        x="date",
        y="daily_pnl",
        title=f"{underlier} Daily PnL",
        labels={"date": "Date", "daily_pnl": "Daily PnL"},
    )
    save_figure(fig, underlier_plot_path(plots_dir, underlier, "daily_pnl.png"))


def plot_drawdown(mtm: pd.DataFrame, underlier: str, plots_dir: str) -> None:
    dd = mtm.copy()
    dd["drawdown"] = compute_drawdown(dd["total_pnl"])

    fig = px.line(
        dd,
        x="timestamp",
        y="drawdown",
        title=f"{underlier} Drawdown",
        labels={"timestamp": "Timestamp", "drawdown": "Drawdown"},
    )
    save_figure(fig, underlier_plot_path(plots_dir, underlier, "drawdown.png"))


def plot_open_position_count(positions: pd.DataFrame, underlier: str, plots_dir: str) -> None:
    fig = px.line(
        positions,
        x="timestamp",
        y="open_count",
        title=f"{underlier} Open Position Count Over Time",
        labels={"timestamp": "Timestamp", "open_count": "Open Position Count"},
    )
    save_figure(fig, underlier_plot_path(plots_dir, underlier, "open_position_count.png"))


def plot_trade_pnl_distribution(trades: pd.DataFrame, underlier: str, plots_dir: str) -> None:
    fig = px.histogram(
        trades,
        x="realized_pnl",
        nbins=50,
        title=f"{underlier} Trade PnL Distribution",
        labels={"realized_pnl": "Realized PnL per Closed Trade"},
    )
    save_figure(fig, underlier_plot_path(plots_dir, underlier, "trade_pnl_distribution.png"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results", help="Directory containing backtest CSV outputs")
    parser.add_argument("--plots-dir", default="plots", help="Directory to save PNG plots")
    args = parser.parse_args()

    ensure_dir(args.plots_dir)

    for underlier in ["NIFTY", "BANKNIFTY"]:
        mtm = load_csv(os.path.join(args.results_dir, f"{underlier}_mtm.csv"))
        trades = load_csv(os.path.join(args.results_dir, f"{underlier}_trades.csv"))
        positions = load_csv(os.path.join(args.results_dir, f"{underlier}_positions.csv"))

        if mtm is None:
            print(f"Skipping {underlier}: missing MTM file")
            continue

        mtm = prepare_mtm(mtm)
        plot_total_pnl(mtm, underlier, args.plots_dir)
        plot_daily_pnl(mtm, underlier, args.plots_dir)
        plot_drawdown(mtm, underlier, args.plots_dir)

        if positions is not None:
            positions = prepare_positions(positions)
            plot_open_position_count(positions, underlier, args.plots_dir)

        if trades is not None and not trades.empty:
            plot_trade_pnl_distribution(trades, underlier, args.plots_dir)

    print(f"Saved plots to: {args.plots_dir}")


if __name__ == "__main__":
    main()