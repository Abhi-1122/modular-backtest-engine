# Test Summary

This file lists what was actually tested on this engine, both through automated tests and through manual validation, and what the outcome was for each one. The goal is to give a reviewer confidence that the results in the results folder reflect correct behavior rather than an untested guess.

## Automated tests

The automated tests live in tests/test_engine.py and are run with pytest. They cover the core mechanical pieces of the engine rather than the full strategy behavior, since those parts are easiest to verify in isolation.

The tests check that option symbols are parsed correctly into strike, expiry, and option type. They check that the portfolio correctly tracks open positions after a sequence of buy and sell fills. They check that mark to market is calculated correctly given a known set of open positions and prices. They check that the data loader correctly removes duplicate timestamps and duplicate end of day rows from raw input. All of these tests passed on the current codebase.

## Manual validation

The manual validation was done through tests/validate_backtest.ipynb, run against the full output for both NIFTY and BANKNIFTY. This was used to check things that are easier to eyeball across a full run than to write as a single unit test.

The first check was confirming that no timestamp in the final output appears more than once, which would have indicated leftover duplicate rows from the raw data. This passed for both indices.

The second check was confirming that at no point during the backtest are more than two option symbols open at the same time. This was the specific bug found earlier, where a strike rotation was briefly leaving four legs open, two old and two new. After fixing the rotation logic to close the old pair and open the new pair at the same timestamp, this check now passes cleanly across the entire run.

The third check was confirming that every rotation event in the trades file lines up with a change in the nearest strike relative to the futures price at that same timestamp, and that the strategy did not rotate when the futures price simply moved closer or further away from the strike it was already holding. This passed after the fix that made the strategy compare against the actual open symbols instead of an internal cached strike value.

The fourth check was confirming that the combined mtm and combined trades files for both indices together match the sum of the individual NIFTY and BANKNIFTY files line by line. This passed, which confirms the combining step is not silently dropping or duplicating rows.

The fifth check was a spot check of a handful of timestamps where a leg's price was missing in the raw data, to confirm that the strategy correctly held its existing position rather than rotating into a pair with an unknown price. This behaved as expected in every case checked.

## Log review

The full run log at logs/run_backtest.log was read through manually for one complete run of both indices to check for any warnings, unexpected skips, or silent failures. No unexpected issues were found. The log now reads as a clean, linear trace of the day by day and timestamp by timestamp execution of the strategy.

## What this does and does not cover

These tests confirm that the engine's internal mechanics are correct and that the strategy behaves the way it was designed to behave. They do not attempt to judge whether the strategy is profitable or whether rolling at the money straddles is a good trading idea in general, since that was outside the scope of what this assignment asked for.
