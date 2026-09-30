"""
strategies.py
Defines champion and challenger strategy configs.

To promote the challenger to champion, change ACTIVE_CHAMPION = CHALLENGER.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class Strategy:
    name: str
    label: str
    signal_fn: Callable    # (ticker, closes, ohlcv) -> float | None
    filters: dict          # informational; gates enforced inside signal_fn / process_ticker
    scoring_label: str
    hold_days: int
    top_n: int
    max_per_sector: int


def _champion_signal(ticker, closes, ohlcv):
    import cup_handle
    result = cup_handle.detect(list(closes.values))
    return result["confidence"] if result["detected"] else None


def _challenger_signal(ticker, closes, ohlcv):
    import momentum_signal
    if ohlcv is None or len(ohlcv) < 252:
        return None
    s = momentum_signal.score(ohlcv)
    return s["composite"] if s is not None else None


CHAMPION = Strategy(
    name="champion",
    label="V1 — Cup & Handle",
    signal_fn=_champion_signal,
    filters={"max_de_ratio": 0.5, "min_5y_return": 0.50, "min_history_days": 60},
    scoring_label="news_index × (0.4 + 0.6 × cup_confidence)",
    hold_days=7,
    top_n=10,
    max_per_sector=3,
)

CHALLENGER = Strategy(
    name="challenger",
    label="V2 — Short-Term Momentum",
    signal_fn=_challenger_signal,
    filters={
        "max_de_ratio": 0.5,
        "min_5y_return": None,
        "min_history_days": 252,
        # Additional gates enforced inside momentum_signal.score():
        #   3/6/12-month returns all positive
        #   RSI(14) between 45 and 70
        #   Price > EMA(20)
        #   ATR(14) > 0.3% of price
    },
    scoring_label="0.30×roc5 + 0.20×roc10 + 0.25×vol_surge + 0.25×ema_alignment",
    hold_days=5,
    top_n=10,
    max_per_sector=3,
)

ACTIVE_CHAMPION = CHAMPION  # set to CHALLENGER to promote
