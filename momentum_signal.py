"""
momentum_signal.py
Computes short-term momentum signals from OHLCV data.

All computations are deterministic from price/volume history — no HTTP calls,
no LLM calls, no randomness.

score() returns None if any hard gate fails, otherwise returns a dict with
all component metrics plus a composite 0-1 score.
"""

import numpy as np
import pandas as pd


# ── Gate thresholds ───────────────────────────────────────────────────────────
RSI_MIN = 45
RSI_MAX = 70
ATR_PCT_MIN = 0.003   # ATR must be > 0.3% of price to be considered tradeable
MIN_HISTORY = 252     # trading days needed for 12-month return check


def compute_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def compute_atr_pct(high: pd.Series, low: pd.Series, close: pd.Series,
                    period: int = 14) -> float:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return float(atr.iloc[-1] / close.iloc[-1])


def compute_period_returns(close: pd.Series) -> dict:
    c = close.values
    return {
        "r3m":  (c[-1] - c[-63])  / c[-63],
        "r6m":  (c[-1] - c[-126]) / c[-126],
        "r12m": (c[-1] - c[-252]) / c[-252],
    }


def compute_roc_norm(close: pd.Series, lookback: int, half_range: float) -> float:
    """Rate of change over `lookback` days, normalized to [0, 1]."""
    roc = (close.iloc[-1] - close.iloc[-lookback]) / close.iloc[-lookback]
    full_range = half_range * 2
    return float(np.clip((roc + half_range) / full_range, 0.0, 1.0))


def compute_volume_surge_norm(volume: pd.Series) -> float:
    vol_5d  = float(volume.iloc[-5:].mean())
    vol_20d = float(volume.iloc[-20:].mean())
    if vol_20d == 0:
        return 0.0
    surge = vol_5d / vol_20d
    # 0.5× → 0.0, 1.0× → 0.2, 3.0× → 1.0
    return float(np.clip((surge - 0.5) / 2.5, 0.0, 1.0))


def compute_ema_alignment(close: pd.Series) -> float:
    ema20  = float(close.ewm(span=20,  adjust=False).mean().iloc[-1])
    ema50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
    ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
    price  = float(close.iloc[-1])

    if price > ema20 and ema20 > ema50 and ema50 > ema200:
        return 1.00
    if price > ema20 and ema20 > ema50:
        return 0.67
    if price > ema20:
        return 0.33
    return 0.00


def ema_alignment_label(alignment: float) -> str:
    labels = {1.00: "full bull stack (>EMA20>50>200)",
              0.67: "above EMA20 & EMA50",
              0.33: "above EMA20 only",
              0.00: "below EMA20"}
    return labels.get(round(alignment, 2), "partial")


def score(ohlcv: pd.DataFrame) -> dict | None:
    """
    Given a DataFrame with Close, High, Low, Volume columns, compute all
    momentum metrics and apply hard gates.

    Returns None if any gate fails (ticker should be excluded).
    Returns a dict of all metrics + composite score if all gates pass.
    """
    if ohlcv is None or len(ohlcv) < MIN_HISTORY:
        return None

    close  = ohlcv["Close"].squeeze()
    high   = ohlcv["High"].squeeze()
    low    = ohlcv["Low"].squeeze()
    volume = ohlcv["Volume"].squeeze()

    # ── Gate 1: 3/6/12-month returns all positive ────────────────────────────
    try:
        returns = compute_period_returns(close)
    except IndexError:
        return None

    if returns["r3m"] <= 0 or returns["r6m"] <= 0 or returns["r12m"] <= 0:
        return None

    # ── Gate 2: RSI in [45, 70] ───────────────────────────────────────────────
    rsi = compute_rsi(close)
    if not (RSI_MIN <= rsi <= RSI_MAX):
        return None

    # ── Gate 3: Price > EMA(20) ───────────────────────────────────────────────
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    if float(close.iloc[-1]) <= ema20:
        return None

    # ── Gate 4: ATR > 0.3% of price ──────────────────────────────────────────
    atr_pct = compute_atr_pct(high, low, close)
    if atr_pct <= ATR_PCT_MIN:
        return None

    # ── Scored components ─────────────────────────────────────────────────────
    roc5_norm         = compute_roc_norm(close, lookback=5,  half_range=0.10)
    roc10_norm        = compute_roc_norm(close, lookback=10, half_range=0.15)
    volume_surge_norm = compute_volume_surge_norm(volume)
    ema_alignment     = compute_ema_alignment(close)

    composite = (
        0.30 * roc5_norm
      + 0.20 * roc10_norm
      + 0.25 * volume_surge_norm
      + 0.25 * ema_alignment
    )

    return {
        "rsi":               round(rsi, 1),
        "atr_pct":           round(atr_pct, 4),
        "r3m":               round(returns["r3m"],  4),
        "r6m":               round(returns["r6m"],  4),
        "r12m":              round(returns["r12m"], 4),
        "roc5":              round((close.iloc[-1] - close.iloc[-5])  / close.iloc[-5],  4),
        "roc10":             round((close.iloc[-1] - close.iloc[-10]) / close.iloc[-10], 4),
        "roc5_norm":         round(roc5_norm,         4),
        "roc10_norm":        round(roc10_norm,        4),
        "volume_surge":      round(float(volume.iloc[-5:].mean()) / max(float(volume.iloc[-20:].mean()), 1), 2),
        "volume_surge_norm": round(volume_surge_norm, 4),
        "ema_alignment":     round(ema_alignment,     2),
        "ema_label":         ema_alignment_label(ema_alignment),
        "composite":         round(composite,         4),
    }
