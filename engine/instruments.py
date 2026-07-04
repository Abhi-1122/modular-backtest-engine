"""
Parsing of option instrument filenames into structured metadata.

Option filename format (no extension):
    <UNDERLIER><EXPIRY:6 digits><STRIKE><CE|PE>

Example:
    NIFTY22110314550PE -> underlier=NIFTY, expiry=221103, strike=14550, opt_type=PE
"""
from dataclasses import dataclass
import re

_OPTION_RE = re.compile(r"^([A-Z]+?)(\d{6})(\d+)(CE|PE)$")


@dataclass(frozen=True)
class OptionInstrument:
    symbol: str          # full filename without extension
    underlier: str
    expiry: str           # YYMMDD as string
    strike: float
    opt_type: str         # "CE" or "PE"


def parse_option_symbol(symbol: str) -> OptionInstrument:
    """Parse an option instrument name into its components.
    """
    match = _OPTION_RE.match(symbol)
    if not match:
        raise ValueError(f"Cannot parse option symbol: {symbol!r}")
    underlier, expiry, strike, opt_type = match.groups()
    return OptionInstrument(
        symbol=symbol,
        underlier=underlier,
        expiry=expiry,
        strike=float(strike),
        opt_type=opt_type,
    )
