"""
backtest.py
Simulates running the Signal screener weekly over the past 52 weeks.
Equal dollar invested in each of the top 10 picks per week, held for one week.
Compares cumulative return against SPY.

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
DETECT_DAYS = 260   # trading days fed into cup_handle.detect()
PRICE_BATCH = 100   # tickers per yfinance batch download


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


# ── Per-week simulation ───────────────────────────────────────────────────────

def simulate_week(
    entry_date: datetime.date,
    exit_date: datetime.date,
    prices: pd.DataFrame,
    filtered_universe: list[dict],
) -> dict | None:
    """
    Run cup & handle detection as of entry_date, pick top 10,
    and compute 1-week returns to exit_date.
    Returns None if no valid picks with exit prices.
    """
    candidates = []

    for row in filtered_universe:
        ticker = row["ticker"]
        if ticker not in prices.columns:
            continue

        # Slice to data visible on entry_date
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
            "ticker": ticker,
            "sector": row["sector"],
            "type": row["type"],
            "confidence": result["confidence"],
            "cup_depth_pct": result["cup_depth_pct"],
            "entry_price": round(entry_price, 2),
        })

    if not candidates:
        return None

    # Sector-capped top N by cup confidence
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

    if not picks:
        return None

    # Attach exit prices and returns
    valid = []
    for p in picks:
        exit_price = close_on(prices, p["ticker"], exit_date)
        if not exit_price:
            continue
        p["exit_price"] = round(exit_price, 2)
        p["weekly_return"] = round((exit_price - p["entry_price"]) / p["entry_price"], 5)
        valid.append(p)

    if not valid:
        return None

    return {
        "date": entry_date,
        "exit_date": exit_date,
        "picks": valid,
        "portfolio_return": float(np.mean([p["weekly_return"] for p in valid])),
        "n_candidates": len(candidates),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n=== Signal Backtest — 52 weeks ===\n")

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

    # 3. Batch download prices (filtered tickers + SPY benchmark)
    all_tickers = [r["ticker"] for r in filtered] + ["SPY"]
    print(f"\nDownloading 2 years of prices for {len(all_tickers)} tickers...")
    prices = batch_download(all_tickers)
    print(f"  Price matrix: {prices.shape[0]} days × {prices.shape[1]} tickers")

    # 4. Weekly simulation loop
    # Need 53 Wednesdays: 52 entry dates + 1 final exit date
    all_wednesdays = get_wednesdays(LOOKBACK_WEEKS + 1)
    entry_dates = all_wednesdays[:-1]

    print(f"\nSimulating {len(entry_dates)} weeks "
          f"({entry_dates[0]} → {entry_dates[-1]})...")

    weekly_results = []
    for i, entry in enumerate(entry_dates):
        exit_date = all_wednesdays[i + 1]
        result = simulate_week(entry, exit_date, prices, filtered)
        if result:
            n = len(result["picks"])
            r = result["portfolio_return"] * 100
            print(f"  {entry}: {n} picks, return={r:+.1f}%")
            weekly_results.append(result)
        else:
            print(f"  {entry}: no picks")

    if not weekly_results:
        print("No results produced. Exiting.")
        return

    # 5. SPY benchmark returns
    for i, week in enumerate(weekly_results):
        spy_entry = close_on(prices, "SPY", week["date"])
        spy_exit  = close_on(prices, "SPY", week["exit_date"])
        if spy_entry and spy_exit:
            week["spy_return"] = (spy_exit - spy_entry) / spy_entry
        else:
            week["spy_return"] = 0.0

    # 6. Cumulative returns
    port_cum = 1.0
    spy_cum  = 1.0
    for week in weekly_results:
        port_cum *= 1 + week["portfolio_return"]
        spy_cum  *= 1 + week["spy_return"]
        week["portfolio_cumulative"] = round((port_cum - 1) * 100, 3)  # % gain
        week["spy_cumulative"]       = round((spy_cum  - 1) * 100, 3)

    # 7. Summary stats
    port_returns = [w["portfolio_return"] for w in weekly_results]
    spy_returns  = [w["spy_return"]       for w in weekly_results]
    wins = sum(p > s for p, s in zip(port_returns, spy_returns))
    best_idx  = int(np.argmax(port_returns))
    worst_idx = int(np.argmin(port_returns))

    summary = {
        "total_return":      round((port_cum - 1) * 100, 2),
        "spy_total_return":  round((spy_cum  - 1) * 100, 2),
        "weeks":             len(weekly_results),
        "start_date":        str(weekly_results[0]["date"]),
        "end_date":          str(weekly_results[-1]["exit_date"]),
        "win_rate_vs_spy":   round(wins / len(weekly_results) * 100, 1),
        "avg_weekly_return": round(float(np.mean(port_returns)) * 100, 2),
        "best_week_return":  round(port_returns[best_idx]  * 100, 2),
        "worst_week_return": round(port_returns[worst_idx] * 100, 2),
        "best_week_date":    str(weekly_results[best_idx]["date"]),
        "worst_week_date":   str(weekly_results[worst_idx]["date"]),
    }

    print(f"\n{'='*40}")
    print(f"Signal total return : {summary['total_return']:+.1f}%")
    print(f"SPY total return    : {summary['spy_total_return']:+.1f}%")
    print(f"Win rate vs SPY     : {summary['win_rate_vs_spy']:.0f}%")
    print(f"Avg weekly return   : {summary['avg_weekly_return']:+.2f}%")
    print(f"Best week           : {summary['best_week_return']:+.1f}% ({summary['best_week_date']})")
    print(f"Worst week          : {summary['worst_week_return']:+.1f}% ({summary['worst_week_date']})")

    # 8. Render HTML report
    import os
    os.makedirs("docs", exist_ok=True)
    backtest_report.save(weekly_results, summary, "docs/backtest.html")
    print("\nDone. Report: docs/backtest.html")


if __name__ == "__main__":
    run()
