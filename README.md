# Modular Backtest Engine

This project is a small backtesting engine built to test an options strategy on index futures data, specifically NIFTY and BANKNIFTY. The engine loads raw tick or minute level data, builds the option universe for the nearest expiry, runs a strategy on it, and produces trade level, position level, and mark to market outputs for review.

The goal was not to build a production trading system. It was to build something clean enough that someone else can read the code, understand the logic in a few minutes, and trust that the numbers coming out the other end actually mean something.

## Running it

Run the backtest from the project root.

```bash
cd modular-backtest-engine
python3.12 run_backtest.py --data-dir allData --out-dir results
```

This reads the raw data from `allData`, runs the strategy for the available indices, and writes the generated outputs into `results`.

To run the automated tests, use:

```bash
cd modular-backtest-engine
python3.12 -m pytest tests/ -v
```

This runs the pytest suite inside the `tests` folder with verbose output.

To generate the plots from the backtest results, run:

```bash
cd modular-backtest-engine/plots
python3.12 generate_plots.py --results-dir ../results --plots-dir ./
```

This reads the files already written in `results` and creates the plots inside the `plots` folder.

## What this repository contains

The engine folder holds the core machinery. data_loader.py reads and cleans the raw data. engine.py drives the event loop, minute by minute, and calls the strategy at each step. instruments.py handles parsing option symbols into strike, expiry, and option type. portfolio.py tracks open positions, fills, and mark to market values. strategy_base.py defines the interface every strategy must follow.

The strategies folder holds the actual trading logic. Right now there is one strategy implemented, rolling_atm_straddle.py, which is the rolling at the money straddle strategy described in the assignment.

The results folder holds the output of a full run for both indices. This includes trades, positions, and mark to market files per index, as well as combined versions across both indices.

The plots folder holds equity curve and mark to market charts generated separately for each index.

The tests folder holds the automated tests in test_engine.py, along with a notebook called validate_backtest.ipynb that was used to manually sanity check the output at a slightly higher level than unit tests usually go.

run_backtest.py is the entry point used to actually run the whole thing end to end.

## Plots

The `plots` folder contains five charts for each index. These are meant to make the backtest easier to review.

### total_pnl.png

This is the cumulative pnl chart. It shows how the overall profit and loss evolved over time across the full backtest, which makes it the quickest way to see the broad performance path of the strategy.

### daily_pnl.png

This shows pnl aggregated at the day level. It helps show whether the overall result came from many small days, a few large days, or an uneven mix of both.

### drawdown.png

This shows the fall from the previous running peak in pnl. It is useful because even a strategy that finishes positive can still go through deep or long losing phases on the way there.

### trade_pnl_distribution.png

This shows the distribution of trade level pnl values. It helps show whether most trades cluster near small gains or losses, or whether a small number of outsized trades drive the result.

### open_position_count.png

This shows how many option positions were open over time. In this project it is especially useful as a sanity check, because the strategy is supposed to hold only one call and one put pair at a time, so this chart helps visually confirm that the position count stayed consistent with the intended logic.

## How the strategy works in short

At every timestamp, the strategy looks at the current futures price and finds the option strike closest to it. It holds one call and one put at that strike. If the futures price moves enough that a different strike becomes the closest one, the strategy closes the old pair and opens the new pair at the same timestamp, so there is never a moment where four legs are open at once and never a moment where the position sits empty for no reason.

## Assumptions

Every assumption made while building this, including some slightly annoying edge cases in the data, is written out separately in [assumptions.md](./assumptions.md).

## Testing and validation

Every test that was run against this engine, both the automated pytest suite and the manual checks done through the validation notebook, is described in [test_summary.md](./test_summary.md). That file lists what was tested, why it mattered, and what the result was. It is meant to be read as evidence that the numbers in the results folder can be trusted
