# Assumptions

This file lists the assumptions made while building the engine and the strategy. Some of these came from the assignment description directly, and some were decisions made to handle real messiness in the data that the assignment did not spell out.

## Expiry handling

Only the nearest expiry is traded at any point in time. If the data contains multiple expiries on a given day, everything except the nearest one is ignored for that day. There is no rollover logic to a further expiry partway through the day, since the assignment scope was limited to the nearest expiry only.

## Strike selection

At every timestamp, the strategy looks at the current futures price and finds the strike that is closest to it among the strikes available for the nearest expiry. If two strikes are exactly equidistant, the lower strike is chosen, mainly to keep the behavior deterministic rather than arbitrary.

## Holding exactly one pair

The strategy always holds exactly one call and one put at the same strike, never more and never less, except for the brief moment during a rotation when the old pair is being closed and the new pair is being opened.

## Rotation timing

When the nearest strike changes, the old call and put are sold and the new call and put are bought at the same timestamp. This was a deliberate choice so that the position is never left with stale legs that no longer reflect the intended strike, and so that the portfolio never briefly holds four legs at once.

## Handling missing prices during rotation

If the target strike changes but the price for the new call or new put is missing at that timestamp, the strategy does nothing and continues holding the existing pair. It waits until both legs of the new pair actually have tradable prices before rotating. This was added after noticing a few timestamps in the raw data where one leg had no quote.

## Source of truth for open positions

The strategy always checks the actual open symbols coming from the portfolio rather than keeping its own separate memory of what it thinks is open. This was a fix made after an earlier version of the strategy kept an internal variable that could drift out of sync with the real portfolio state, which caused incorrect rotations.

## Duplicate timestamps in raw data

The raw data occasionally contained duplicate timestamps, and in some cases duplicate end of day snapshots. These duplicates are removed during the data loading step before anything is passed to the strategy, so the engine never processes the same moment in time twice.

## Quantity per leg

Each leg of the straddle is traded with a fixed quantity of one lot per instrument. This kept the mark to market and position tracking simple and easy to verify by hand, since the assignment did not specify a particular sizing scheme.

## Scope of instruments

Only NIFTY and BANKNIFTY are handled. No other indices or stock options are supported, since these were the only two provided in the data.

## Mark to market calculation

Mark to market is calculated at every timestamp using the last available price for each open leg. If a price is missing at a given timestamp for a leg that is still open, the last known price for that leg is carried forward rather than treating the position as having no value.
