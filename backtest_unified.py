"""
backtest_unified.py
Head-to-head backtest: Champion (V1 cup & handle) vs Challenger (V2 momentum).

Methodology — both strategies tested on identical terms:
  - Same universe, same debt filter, same weekly entry dates
  - Entry: Wednesday close. Exit: following Wednesday close (~5 trading days).
  - Capital: $1,000/week equal-weight across top-10 sector-capped picks.
  - Benchmark: SPY over same window.
  - Signal computed on data sliced to [: entry_date] — no lookahead.

Additional metric — days to +5%:
  - For each pick, scan forward daily closes from entry until price >= entry * 1.05.
  - Cap: 63 trading days (~3 calendar months). Beyond cap → "not reached".
  - Truncated: if fewer than 63 trading days of forward data exist (picks near end of
    simulation), the pick is excluded from both the % and average calculations.
  - Reported separately: "X% reached +5%, avg Y trading days for those that did."

Limitations (disclosed in report):
  - Champion signal uses cup_confidence only — news excluded (no historical free API).
    Live V1 formula multiplies by news_index; backtest tests a degraded proxy.
  - Debt/equity uses current values (mild look-ahead bias, symmetric across strategies).
  - Universe = current S&P 500 constituents (survivorship bias, symmetric).
  - No transaction costs or slippage.
"""

import datetime
import json
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

import cup_handle
import momentum_signal
import backtest_report_unified
from screen import (
    load_universe,
    fetch_fundamentals,
    passes_debt_filter,
    MAX_PER_SECTOR,
    WORKERS,
)

warnings.filterwarnings("ignore")

TOP_N         = 10
LOOKBACK_WEEKS = 52
PRICE_BATCH   = 100
WEEKLY_INVEST = 1_000.0
FIVE_PCT_CAP  = 63   # trading days; beyond this → "not reached"


# ── Date helpers ──────────────────────────────────────────────────────────────

def get_wednesdays(n: int) -> list[datetime.date]:
    today = datetime.date.today()
    offset = (today.weekday() - 2) % 7
    most_recent = today - datetime.timedelta(days=offset)
    if most_recent == today:
        most_recent -= datetime.timedelta(weeks=1)
    return sorted(most_recent - datetime.timedelta(weeks=i) for i in range(n))


# ── OHLCV data ────────────────────────────────────────────────────────────────

def batch_download_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Download 2 years of OHLCV. Returns {ticker: DataFrame} with date index."""
    cache: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), PRICE_BATCH):
        batch = tickers[i : i + PRICE_BATCH]
        print(f"  Downloading {i+1}–{min(i+PRICE_BATCH, len(tickers))} / {len(tickers)}...")
        raw = yf.download(batch, period="2y", auto_adjust=True, progress=False)
        if raw.empty:
            continue
        raw.index = pd.to_datetime(raw.index).date
        for ticker in batch:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close","Volume"]]
                else:
                    df = raw[["Open","High","Low","Close","Volume"]]
                df = df.dropna(how="all")
                if len(df) >= 60:
                    cache[ticker] = df
            except (KeyError, Exception):
                pass
    return cache


def _ts(d: datetime.date) -> pd.Timestamp:
    return pd.Timestamp(d)


def close_on(cache: dict, ticker: str, target: datetime.date) -> float | None:
    df = cache.get(ticker)
    if df is None:
        return None
    col = df["Close"][pd.to_datetime(df.index) <= _ts(target)].dropna()
    return float(col.iloc[-1]) if not col.empty else None


# ── Days-to-5% metric ─────────────────────────────────────────────────────────

def days_to_5pct(
    cache: dict,
    ticker: str,
    entry_date: datetime.date,
    entry_price: float,
    cap: int = FIVE_PCT_CAP,
) -> tuple[int | None, bool, bool]:
    """
    Scan forward closes from entry_date for ticker reaching +5%.

    Returns (days, reached, truncated):
      days      — trading days until +5% was hit (None if not reached)
      reached   — True if price hit entry_price * 1.05 within cap days
      truncated — True if fewer than cap days of forward data exist
                  (pick excluded from aggregate stats)
    """
    df = cache.get(ticker)
    if df is None:
        return None, False, True

    forward = df["Close"][pd.to_datetime(df.index) > _ts(entry_date)].dropna()
    target  = entry_price * 1.05

    if len(forward) < cap:
        # Not enough forward data to make a full assessment
        return None, False, True

    for i, price in enumerate(forward.iloc[:cap]):
        if float(price) >= target:
            return i + 1, True, False

    return None, False, False   # cap exhausted, not reached


# ── Signal detection ──────────────────────────────────────────────────────────

def detect_champion(
    entry_date: datetime.date,
    cache: dict,
    universe: list[dict],
) -> tuple[list[dict], int]:
    """Cup & handle picks as of entry_date. Score = cup_confidence (news excluded)."""
    candidates = []
    for row in universe:
        ticker = row["ticker"]
        df = cache.get(ticker)
        if df is None:
            continue
        col = df["Close"][pd.to_datetime(df.index) <= _ts(entry_date)].dropna()
        if len(col) < 60:
            continue
        recent = col.iloc[-260:] if len(col) >= 260 else col
        result = cup_handle.detect(list(recent.values))
        if not result["detected"]:
            continue
        entry_price = close_on(cache, ticker, entry_date)
        if not entry_price:
            continue
        candidates.append({
            "ticker":        ticker,
            "sector":        row["sector"],
            "type":          row["type"],
            "score":         result["confidence"],
            "confidence":    result["confidence"],
            "cup_depth_pct": result["cup_depth_pct"],
            "entry_price":   round(entry_price, 2),
        })

    return _select_top(candidates, "score"), len(candidates)


def detect_challenger(
    entry_date: datetime.date,
    cache: dict,
    universe: list[dict],
) -> tuple[list[dict], int]:
    """Momentum picks as of entry_date. Full composite score, all gates applied."""
    candidates = []
    for row in universe:
        ticker = row["ticker"]
        df = cache.get(ticker)
        if df is None:
            continue
        df_slice = df[pd.to_datetime(df.index) <= _ts(entry_date)]
        if len(df_slice) < 252:
            continue
        sig = momentum_signal.score(df_slice)
        if sig is None:
            continue
        entry_price = close_on(cache, ticker, entry_date)
        if not entry_price:
            continue
        candidates.append({
            "ticker":        ticker,
            "sector":        row["sector"],
            "type":          row["type"],
            "score":         sig["composite"],
            "composite":     sig["composite"],
            "rsi":           sig["rsi"],
            "roc5":          sig["roc5"],
            "ema_label":     sig["ema_label"],
            "volume_surge":  sig["volume_surge"],
            "entry_price":   round(entry_price, 2),
        })

    return _select_top(candidates, "score"), len(candidates)


def _select_top(candidates: list[dict], score_key: str) -> list[dict]:
    candidates.sort(key=lambda x: x[score_key], reverse=True)
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
    return picks


# ── Main ──────────────────────────────────────────────────────────────────────

def run(lookback_weeks: int = LOOKBACK_WEEKS) -> None:
    print("\n=== Unified Backtest — Champion vs Challenger (5-day holds) ===\n")

    # 1. Universe + debt filter
    universe = load_universe()
    print(f"Universe: {len(universe)} tickers")

    print("\nFetching fundamentals...")
    fundamentals: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_fundamentals, row.ticker): row
                   for row in universe.itertuples()}
        for i, future in enumerate(as_completed(futures)):
            row = futures[future]
            res = future.result()
            if res:
                res["sector"] = row.sector
                res["type"]   = row.type
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

    # 2. Download OHLCV
    all_tickers = [r["ticker"] for r in filtered] + ["SPY"]
    print(f"\nDownloading 2 years of OHLCV for {len(all_tickers)} tickers...")
    cache = batch_download_ohlcv(all_tickers)
    print(f"  Cached {len(cache)} tickers")

    # 3. Weekly simulation
    all_wednesdays = get_wednesdays(lookback_weeks + 1)
    entry_dates    = all_wednesdays[:-1]

    print(f"\nSimulating {len(entry_dates)} weeks "
          f"({entry_dates[0]} → {entry_dates[-1]})...\n")

    weekly_results = []

    for i, entry in enumerate(entry_dates):
        exit_date = all_wednesdays[i + 1]

        champ_picks,  n_champ  = detect_champion(entry,   cache, filtered)
        chall_picks,  n_chall  = detect_challenger(entry, cache, filtered)

        def enrich_picks(picks: list[dict]) -> list[dict]:
            enriched = []
            for p in picks:
                exit_price = close_on(cache, p["ticker"], exit_date)
                if not exit_price:
                    continue
                pnl_pct = (exit_price - p["entry_price"]) / p["entry_price"]
                days, reached, truncated = days_to_5pct(
                    cache, p["ticker"], entry, p["entry_price"]
                )
                enriched.append({
                    **p,
                    "exit_price":  round(exit_price, 2),
                    "pnl_pct":     round(pnl_pct, 4),
                    "days_to_5pct":    days,
                    "reached_5pct":    reached,
                    "truncated_5pct":  truncated,
                })
            return enriched

        champ_picks  = enrich_picks(champ_picks)
        chall_picks  = enrich_picks(chall_picks)

        def avg_return(picks):
            r = [p["pnl_pct"] for p in picks]
            return float(np.mean(r)) if r else 0.0

        champ_ret = avg_return(champ_picks)
        chall_ret = avg_return(chall_picks)

        spy_entry = close_on(cache, "SPY", entry)
        spy_exit  = close_on(cache, "SPY", exit_date)
        spy_ret   = (spy_exit - spy_entry) / spy_entry if (spy_entry and spy_exit) else 0.0

        weekly_results.append({
            "entry_date":       entry,
            "exit_date":        exit_date,
            "champion_picks":   champ_picks,
            "challenger_picks": chall_picks,
            "n_champion_cand":  n_champ,
            "n_challenger_cand":n_chall,
            "champion_return":  round(champ_ret,  4),
            "challenger_return":round(chall_ret,  4),
            "spy_return":       round(spy_ret,    4),
            "champion_beat_spy":    champ_ret > spy_ret,
            "challenger_beat_spy":  chall_ret > spy_ret,
        })

        c_beat = "✓" if champ_ret  > spy_ret else "✗"
        h_beat = "✓" if chall_ret  > spy_ret else "✗"
        print(f"  {entry} | "
              f"Champ {champ_ret:+.2%} {c_beat}  "
              f"Chall {chall_ret:+.2%} {h_beat}  "
              f"SPY {spy_ret:+.2%}  | "
              f"{len(champ_picks)}/{len(chall_picks)} picks")

    if not weekly_results:
        print("No results. Exiting.")
        return

    # 4. Aggregate stats
    def agg_strategy(pick_key: str, return_key: str, beat_key: str) -> dict:
        all_picks   = [p for w in weekly_results for p in w[pick_key]]
        all_returns = [w[return_key] for w in weekly_results]
        beat_count  = sum(w[beat_key] for w in weekly_results)

        # Days-to-5% — exclude truncated picks
        assessable = [p for p in all_picks if not p["truncated_5pct"]]
        reached    = [p for p in assessable if p["reached_5pct"]]
        not_reached = [p for p in assessable if not p["reached_5pct"]]

        pct_reached = len(reached) / len(assessable) if assessable else 0.0
        avg_days    = (float(np.mean([p["days_to_5pct"] for p in reached]))
                       if reached else None)

        def rolling_12w(returns):
            r12 = returns[-12:]
            return float(np.prod([1 + r for r in r12]) ** (1 / len(r12)) - 1)

        return {
            "avg_return":       round(float(np.mean(all_returns)), 4),
            "win_rate":         round(beat_count / len(weekly_results), 3),
            "rolling_12w":      round(rolling_12w(all_returns), 4),
            "best_week":        max(all_returns),
            "worst_week":       min(all_returns),
            "total_picks":      len(all_picks),
            "assessable_picks": len(assessable),
            "reached_5pct_n":   len(reached),
            "not_reached_5pct_n": len(not_reached),
            "truncated_5pct_n": len(all_picks) - len(assessable),
            "pct_reached_5pct": round(pct_reached, 3),
            "avg_days_to_5pct": round(avg_days, 1) if avg_days is not None else None,
        }

    spy_returns = [w["spy_return"] for w in weekly_results]

    summary = {
        "champion":   agg_strategy("champion_picks",   "champion_return",   "champion_beat_spy"),
        "challenger": agg_strategy("challenger_picks",  "challenger_return", "challenger_beat_spy"),
        "spy": {
            "avg_return":  round(float(np.mean(spy_returns)), 4),
            "rolling_12w": round(float(np.prod([1+r for r in spy_returns[-12:]]) ** (1/12) - 1), 4),
        },
        "weeks":      len(weekly_results),
        "start_date": str(weekly_results[0]["entry_date"]),
        "end_date":   str(weekly_results[-1]["exit_date"]),
        "weekly_invest": WEEKLY_INVEST,
        "five_pct_cap_days": FIVE_PCT_CAP,
    }

    # 5. Print summary
    print(f"\n{'='*60}")
    for name in ("champion", "challenger"):
        s = summary[name]
        days_str = (f"{s['avg_days_to_5pct']} days"
                    if s['avg_days_to_5pct'] is not None else "—")
        print(f"\n{name.upper()}")
        print(f"  Avg 5-day return    : {s['avg_return']:+.2%}")
        print(f"  Win rate vs SPY     : {s['win_rate']:.0%}")
        print(f"  Rolling 12w         : {s['rolling_12w']:+.2%}")
        print(f"  Reached +5%         : {s['pct_reached_5pct']:.0%} "
              f"({s['reached_5pct_n']}/{s['assessable_picks']} assessable picks)")
        print(f"  Avg days to +5%     : {days_str}")
    print(f"\nSPY avg 5-day return: {summary['spy']['avg_return']:+.2%}")

    # 6. Save summary JSON
    os.makedirs("docs", exist_ok=True)
    summary_path = "docs/backtest_unified_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nSummary → {summary_path}")

    # 7. Render HTML report
    backtest_report_unified.save(weekly_results, summary, "docs/backtest_unified.html")
    print("Report  → docs/backtest_unified.html")


if __name__ == "__main__":
    run()
