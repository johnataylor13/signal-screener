"""
backtest.py
Simulates running the Signal screener weekly over the past 52 weeks.
Buy-and-hold DCA: $1,000/week deployed into Signal picks (never sold),
compared against $1,000/week into SPY and $1,000/week into the S&P 500 index.

Limitations (shown in report):
  - News surge excluded — no historical free API
  - Debt/equity uses current values, not historical
  - Universe uses current S&P 500 constituents (survivorship bias)
"""

import datetime
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

import cup_handle
import backtest_report
from screen import (
    load_universe,
    fetch_fundamentals,
    passes_debt_filter,
    MAX_PER_SECTOR,
    WORKERS,
)

warnings.filterwarnings("ignore")

TOP_N = 10
LOOKBACK_WEEKS = 52
DETECT_DAYS = 260    # trading days fed into cup_handle.detect()
PRICE_BATCH = 100    # tickers per yfinance batch download
WEEKLY_INVEST = 1_000.0  # dollars deployed per strategy per week


# ── Date helpers ──────────────────────────────────────────────────────────────

def get_wednesdays(n: int) -> list[datetime.date]:
    """Return the last n Wednesdays in chronological order (oldest first)."""
    today = datetime.date.today()
    offset = (today.weekday() - 2) % 7          # days since last Wednesday
    most_recent = today - datetime.timedelta(days=offset)
    if most_recent == today:
        most_recent -= datetime.timedelta(weeks=1)
    return sorted(most_recent - datetime.timedelta(weeks=i) for i in range(n))


# ── Price data ────────────────────────────────────────────────────────────────

def batch_download(tickers: list[str]) -> pd.DataFrame:
    """
    Download 2 years of adjusted daily close prices for all tickers.
    Batches to avoid yfinance payload limits.
    Returns a DataFrame: date index × ticker columns.
    """
    frames = []
    for i in range(0, len(tickers), PRICE_BATCH):
        batch = tickers[i : i + PRICE_BATCH]
        print(f"  Downloading prices {i+1}–{min(i+PRICE_BATCH, len(tickers))} / {len(tickers)}...")
        raw = yf.download(batch, period="2y", auto_adjust=True, progress=False)
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if not isinstance(raw.columns, pd.MultiIndex):
            close.columns = batch
        frames.append(close)
    combined = pd.concat(frames, axis=1)
    combined.index = pd.to_datetime(combined.index).date
    return combined


def close_on(prices: pd.DataFrame, ticker: str, target: datetime.date) -> float | None:
    """Last available close price on or before target date."""
    if ticker not in prices.columns:
        return None
    col = prices[ticker].dropna()
    available = col[col.index <= target]
    return float(available.iloc[-1]) if not available.empty else None


# ── Pattern detection ─────────────────────────────────────────────────────────

def detect_picks(
    entry_date: datetime.date,
    prices: pd.DataFrame,
    filtered_universe: list[dict],
) -> tuple[list[dict], int]:
    """
    Run cup & handle detection as of entry_date using only data visible then.
    Returns (sector-capped top-N picks with entry prices, n_candidates).
    """
    candidates = []

    for row in filtered_universe:
        ticker = row["ticker"]
        if ticker not in prices.columns:
            continue

        col = prices[ticker].dropna()
        col = col[col.index <= entry_date]
        if len(col) < 60:
            continue

        recent = col.iloc[-DETECT_DAYS:] if len(col) >= DETECT_DAYS else col
        result = cup_handle.detect(list(recent.values))
        if not result["detected"]:
            continue

        entry_price = close_on(prices, ticker, entry_date)
        if not entry_price:
            continue

        candidates.append({
            "ticker":       ticker,
            "sector":       row["sector"],
            "type":         row["type"],
            "confidence":   result["confidence"],
            "cup_depth_pct": result["cup_depth_pct"],
            "entry_price":  round(entry_price, 2),
        })

    if not candidates:
        return [], 0

    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    sector_counts: dict[str, int] = {}
    picks = []
    for c in candidates:
        count = sector_counts.get(c["sector"], 0)
        if count >= MAX_PER_SECTOR:
            continue
        sector_counts[c["sector"]] = count + 1
        picks.append(c)
        if len(picks) >= TOP_N:
            break

    return picks, len(candidates)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n=== Signal Backtest — 52 weeks (buy-and-hold DCA) ===\n")

    # 1. Universe
    universe = load_universe()
    print(f"Universe: {len(universe)} tickers")

    # 2. Fundamentals + debt filter
    print("\nFetching fundamentals for debt filter...")
    fundamentals: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_fundamentals, row.ticker): row
                   for row in universe.itertuples()}
        for i, future in enumerate(as_completed(futures)):
            row = futures[future]
            res = future.result()
            if res:
                res["sector"] = row.sector
                res["type"] = row.type
                fundamentals[row.ticker] = res
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(universe)} fetched...")

    debt_ok = {
        k: v for k, v in fundamentals.items()
        if passes_debt_filter(v.get("debt_equity"), v["type"])
    }
    print(f"  After debt filter: {len(debt_ok)} tickers")

    filtered = [
        {"ticker": k, "sector": v["sector"], "type": v["type"]}
        for k, v in debt_ok.items()
    ]

    # 3. Batch download prices (filtered tickers + benchmarks)
    all_tickers = [r["ticker"] for r in filtered] + ["SPY", "^GSPC", "QQQ"]
    print(f"\nDownloading 2 years of prices for {len(all_tickers)} tickers...")
    prices = batch_download(all_tickers)
    print(f"  Price matrix: {prices.shape[0]} days × {prices.shape[1]} tickers")

    # 4. Weekly simulation — buy-and-hold DCA
    # Need 53 Wednesdays: 52 entry/buy dates + 1 final valuation date
    all_wednesdays = get_wednesdays(LOOKBACK_WEEKS + 1)
    entry_dates = all_wednesdays[:-1]

    print(f"\nSimulating {len(entry_dates)} weeks "
          f"({entry_dates[0]} → {entry_dates[-1]})...")

    # Running positions (never sold)
    signal_positions: list[dict] = []  # {ticker, shares}
    spy_shares   = 0.0
    sp500_shares = 0.0
    qqq_shares   = 0.0

    weekly_results = []
    for i, entry in enumerate(entry_dates):
        exit_date = all_wednesdays[i + 1]

        picks, n_cand = detect_picks(entry, prices, filtered)

        # Deploy $WEEKLY_INVEST equally across Signal picks
        if picks:
            per_pick = round(WEEKLY_INVEST / len(picks), 4)
            for p in picks:
                shares = per_pick / p["entry_price"]
                p["cost"]   = per_pick
                p["shares"] = round(shares, 6)
                signal_positions.append({"ticker": p["ticker"], "shares": shares})

        # Deploy $WEEKLY_INVEST into SPY
        spy_ep = close_on(prices, "SPY", entry)
        if spy_ep:
            spy_shares += WEEKLY_INVEST / spy_ep

        # Deploy $WEEKLY_INVEST into ^GSPC (conceptual index position)
        sp500_ep = close_on(prices, "^GSPC", entry)
        if sp500_ep:
            sp500_shares += WEEKLY_INVEST / sp500_ep

        # Deploy $WEEKLY_INVEST into QQQ
        qqq_ep = close_on(prices, "QQQ", entry)
        if qqq_ep:
            qqq_shares += WEEKLY_INVEST / qqq_ep

        # Value all portfolios at end of week (exit_date)
        signal_val = sum(
            pos["shares"] * (close_on(prices, pos["ticker"], exit_date) or 0.0)
            for pos in signal_positions
        )

        spy_xp   = close_on(prices, "SPY",   exit_date)
        sp500_xp = close_on(prices, "^GSPC", exit_date)
        qqq_xp   = close_on(prices, "QQQ",   exit_date)
        spy_val   = spy_shares   * spy_xp   if spy_xp   else 0.0
        sp500_val = sp500_shares * sp500_xp if sp500_xp else 0.0
        qqq_val   = qqq_shares   * qqq_xp   if qqq_xp   else 0.0

        total_deployed = (i + 1) * WEEKLY_INVEST

        weekly_results.append({
            "date":           entry,
            "exit_date":      exit_date,
            "picks":          picks,
            "n_candidates":   n_cand,
            "signal_value":   round(signal_val, 2),
            "spy_value":      round(spy_val, 2),
            "sp500_value":    round(sp500_val, 2),
            "qqq_value":      round(qqq_val, 2),
            "total_deployed": round(total_deployed, 2),
        })

        n_p = len(picks)
        print(f"  {entry}: {n_p:2d} picks | "
              f"Signal ${signal_val:>8,.0f} | "
              f"SPY ${spy_val:>8,.0f} | "
              f"S&P ${sp500_val:>8,.0f} | "
              f"QQQ ${qqq_val:>8,.0f} | "
              f"Deployed ${total_deployed:>7,.0f}")

    if not weekly_results:
        print("No results produced. Exiting.")
        return

    # 5. Summary stats
    final       = weekly_results[-1]
    total_dep   = final["total_deployed"]
    signal_fin  = final["signal_value"]
    spy_fin     = final["spy_value"]
    sp500_fin   = final["sp500_value"]
    qqq_fin     = final["qqq_value"]

    def gain_pct(val: float) -> float:
        return (val - total_dep) / total_dep * 100 if total_dep else 0.0

    wins_vs_spy = sum(w["signal_value"] > w["spy_value"] for w in weekly_results)

    summary = {
        "total_deployed":   round(total_dep,  2),
        "signal_final":     round(signal_fin, 2),
        "spy_final":        round(spy_fin,    2),
        "sp500_final":      round(sp500_fin,  2),
        "qqq_final":        round(qqq_fin,    2),
        "signal_gain_pct":  round(gain_pct(signal_fin), 2),
        "spy_gain_pct":     round(gain_pct(spy_fin),    2),
        "sp500_gain_pct":   round(gain_pct(sp500_fin),  2),
        "qqq_gain_pct":     round(gain_pct(qqq_fin),    2),
        "weeks":            len(weekly_results),
        "start_date":       str(weekly_results[0]["date"]),
        "end_date":         str(final["exit_date"]),
        "win_rate_vs_spy":  round(wins_vs_spy / len(weekly_results) * 100, 1),
        "weekly_invest":    WEEKLY_INVEST,
    }

    print(f"\n{'='*48}")
    print(f"Total deployed       : ${total_dep:>10,.0f}")
    print(f"Signal final value   : ${signal_fin:>10,.0f}  ({gain_pct(signal_fin):+.1f}%)")
    print(f"SPY final value      : ${spy_fin:>10,.0f}  ({gain_pct(spy_fin):+.1f}%)")
    print(f"S&P 500 final value  : ${sp500_fin:>10,.0f}  ({gain_pct(sp500_fin):+.1f}%)")
    print(f"QQQ final value      : ${qqq_fin:>10,.0f}  ({gain_pct(qqq_fin):+.1f}%)")
    print(f"Win rate vs SPY      : {summary['win_rate_vs_spy']:.0f}%")

    # 6. Render HTML report
    import os
    os.makedirs("docs", exist_ok=True)
    backtest_report.save(weekly_results, summary, "docs/backtest.html")
    print("\nDone. Report: docs/backtest.html")


if __name__ == "__main__":
    run()
