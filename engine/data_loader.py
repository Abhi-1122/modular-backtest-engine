
"""
Data loading utilities for the options + futures backtest.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .instruments import OptionInstrument, parse_option_symbol

COLUMNS = ["Date", "Time", "Price", "Volume", "OpenInterest"]


@dataclass
class DayData:
    date: str
    futures: Dict[str, pd.DataFrame]
    options: Dict[str, pd.DataFrame]
    instruments: Dict[str, OptionInstrument]


def _find_file_case_insensitive(directory: str, target_name: str) -> Optional[str]:
    if not os.path.isdir(directory):
        return None
    target = target_name.lower()
    for name in os.listdir(directory):
        if name.lower() == target:
            return os.path.join(directory, name)
    return None


def _read_tick_csv(path: str) -> pd.DataFrame:
    # Read raw and decide whether header is present.
    raw = pd.read_csv(path)
    if list(raw.columns[:5]) == COLUMNS:
        df = raw[COLUMNS].copy()
    else:
        df = pd.read_csv(path, header=None, names=COLUMNS)

    df["Date"] = df["Date"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["Time"] = df["Time"].astype(str)
    ts = pd.to_datetime(
        df["Date"].astype(str) + df["Time"].astype(str),
        format="%Y%m%d%H:%M:%S",
        errors="coerce",
    )
    df = df.loc[~ts.isna()].copy()
    ts = ts[~ts.isna()]
    df.insert(0, "Timestamp", ts)
    df = df.drop(columns=["Date", "Time"]).set_index("Timestamp").sort_index()
    return df


def list_trading_dates(all_data_dir: str) -> List[str]:
    dates = []
    if not os.path.isdir(all_data_dir):
        return dates
    for name in os.listdir(all_data_dir):
        if name.startswith("NSE_"):
            dates.append(name.replace("NSE_", ""))
    return sorted(dates)


def load_day(all_data_dir: str, date: str, underliers: List[str]) -> DayData:
    day_dir = os.path.join(all_data_dir, f"NSE_{date}")
    futures_dir = os.path.join(day_dir, "Futures (Continuous)")
    options_dir = os.path.join(day_dir, "Options")

    futures: Dict[str, pd.DataFrame] = {}
    for underlier in underliers:
        fpath = None
        if futures_dir:
            fpath = _find_file_case_insensitive(futures_dir, f"{underlier}-I.csv")
        if fpath and os.path.exists(fpath):
            futures[underlier] = _read_tick_csv(fpath)

    options: Dict[str, pd.DataFrame] = {}
    instruments: Dict[str, OptionInstrument] = {}
    if options_dir and os.path.isdir(options_dir):
        for fname in os.listdir(options_dir):
            if not fname.lower().endswith('.csv'):
                continue
            symbol = fname[:-4]
            try:
                inst = parse_option_symbol(symbol)
            except ValueError:
                continue
            if inst.underlier not in underliers:
                continue
            options[symbol] = _read_tick_csv(os.path.join(options_dir, fname))
            instruments[symbol] = inst

    return DayData(date=date, futures=futures, options=options, instruments=instruments)
