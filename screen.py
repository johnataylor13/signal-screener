"""
screen.py
Weekly stock + ETF screener.

Steps:
  1. Load universe (S&P 500 + curated ETFs)
  2. Filter by debt/equity <= 0.5 and 5Y return >= 50%
  3. Run cup & handle detection on 6-month daily price history
  4. Fetch news surge ratio via NewsAPI
  5. Score, apply sector cap (max 3 per sector), select top 10
  6. Render and save HTML report

Requirements: see requirements.txt
Set NEWS_API_KEY environment variable before running.
"""

import io
import os
import time
import datetime
import warnings
import xml.etree.ElementTree as ET
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

import cup_handle
import report as report_module

warnings.filterwarnings("ignore")

# ── Config ────────────────────────────────────────────────────────────────────
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
NEWS_MIN_PREV = 3           # prior-week article floor; below this, no surge multiplier
NEWS_MAX_SURGE = 3.0        # cap surge at 3x so thin-coverage stocks can't dominate
MAX_DE_RATIO = 0.5
MIN_5Y_RETURN = 0.50        # 50%
MAX_PER_SECTOR = 3
TOP_N = 10
PRICE_HISTORY_DAYS = 400    # ~18 months of trading days to pull
WORKERS = 8                 # parallel yfinance fetches

# ── ETF universe ──────────────────────────────────────────────────────────────
CURATED_ETFS = [
    ("VIG",  "Multi-Sector",          "Vanguard Dividend Appreciation ETF"),
    ("RSP",  "Multi-Sector",          "Invesco S&P 500 Equal Weight ETF"),
    ("XLI",  "Industrials",           "Industrial Select Sector SPDR ETF"),
    ("XLV",  "Healthcare",            "Health Care Select Sector SPDR ETF"),
    ("XLE",  "Energy",                "Energy Select Sector SPDR ETF"),
    ("XLF",  "Financials",            "Financial Select Sector SPDR ETF"),
    ("XLK",  "Technology",            "Technology Select Sector SPDR ETF"),
    ("XLY",  "Consumer Discretionary","Consumer Discretionary Select Sector SPDR ETF"),
    ("XLP",  "Consumer Staples",      "Consumer Staples Select Sector SPDR ETF"),
    ("XLRE", "Real Estate",           "Real Estate Select Sector SPDR ETF"),
    ("XLB",  "Materials",             "Materials Select Sector SPDR ETF"),
    ("XLU",  "Utilities",             "Utilities Select Sector SPDR ETF"),
    ("VEA",  "International",         "Vanguard FTSE Developed Markets ETF"),
    ("VWO",  "International",         "Vanguard FTSE Emerging Markets ETF"),
    ("IWM",  "Multi-Sector",          "iShares Russell 2000 ETF"),
    ("QQQ",  "Technology",            "Invesco QQQ Trust"),
    ("SCHD", "Multi-Sector",          "Schwab US Dividend Equity ETF"),
    ("VNQ",  "Real Estate",           "Vanguard Real Estate ETF"),
    ("GLD",  "Commodities",           "SPDR Gold Shares"),
    ("BND",  "Fixed Income",          "Vanguard Total Bond Market ETF"),
    ("AGG",  "Fixed Income",          "iShares Core US Aggregate Bond ETF"),
    ("VGT",  "Technology",            "Vanguard Information Technology ETF"),
    ("SOXX", "Technology",            "iShares Semiconductor ETF"),
    ("IBB",  "Healthcare",            "iShares Biotechnology ETF"),
    ("IYT",  "Industrials",           "iShares Transportation Average ETF"),
]

ETF_TICKERS = {t[0] for t in CURATED_ETFS}
ETF_META = {t[0]: {"sector": t[1], "name": t[2]} for t in CURATED_ETFS}


# ── Step 1: Load universe ─────────────────────────────────────────────────────
def load_sp500() -> pd.DataFrame:
    """Pull S&P 500 constituents from Wikipedia."""
    print("Loading S&P 500 constituents...")
    try:
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (signal-screener/1.0; +https://github.com)"},
            timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0][["Symbol", "GICS Sector", "Security"]].copy()
        df.columns = ["ticker", "sector", "name"]
        df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
        df["type"] = "stock"
        return df
    except Exception as e:
        print(f"  Warning: Could not load S&P 500 from Wikipedia: {e}")
        return pd.DataFrame(columns=["ticker", "sector", "name", "type"])


def load_universe() -> pd.DataFrame:
    sp500 = load_sp500()

    etf_rows = []
    for ticker, meta in ETF_META.items():
        etf_rows.append({
            "ticker": ticker,
            "sector": meta["sector"],
            "name": meta["name"],
            "type": "etf"
        })
    etfs = pd.DataFrame(etf_rows)

    universe = pd.concat([sp500, etfs], ignore_index=True)
    print(f"Universe: {len(universe)} tickers ({len(sp500)} stocks + {len(etfs)} ETFs)")
    return universe


# ── Step 2: Fundamentals filter ───────────────────────────────────────────────
def fetch_fundamentals(ticker: str) -> dict | None:
    """Returns dict with debt_equity, return_5y, price, description, or None on failure."""
    try:
        t = yf.Ticker(ticker)
        info = t.info

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return None

        # Debt/equity — ETFs will have None
        de = info.get("debtToEquity")
        if de is not None:
            de = de / 100  # yfinance returns as percentage (e.g. 45.2 = 0.452)

        # 5Y return — use 52wk as proxy if 5Y not available, else pull history
        # We'll compute properly from price history later; here just get a rough filter
        # using fiftyTwoWeekLow as a sanity check
        desc = info.get("longBusinessSummary", "")
        short_name = info.get("shortName", ticker)

        return {
            "ticker": ticker,
            "price": price,
            "debt_equity": de,
            "desc": desc[:400] if desc else "",
            "short_name": short_name,
        }
    except Exception:
        return None


def passes_debt_filter(de: float | None, ticker_type: str) -> bool:
    if ticker_type == "etf":
        return True  # ETFs have no direct debt
    if de is None:
        return False  # Can't verify, skip
    return de <= MAX_DE_RATIO


# ── Step 3: Price history + returns + cup & handle ────────────────────────────
def fetch_price_history(ticker: str, days: int = PRICE_HISTORY_DAYS) -> pd.Series | None:
    """Returns a daily close price Series."""
    try:
        end = datetime.date.today()
        start = end - datetime.timedelta(days=days + 10)
        hist = yf.download(ticker, start=str(start), end=str(end),
                           progress=False, auto_adjust=True)
        if hist.empty or len(hist) < 60:
            return None
        return hist["Close"].squeeze()
    except Exception:
        return None


def compute_returns(closes: pd.Series) -> dict:
    """Compute 1M, 1Y, 3Y, 5Y returns from a daily close series."""
    def _ret(days):
        if len(closes) < days:
            return None
        start_price = closes.iloc[-days]
        end_price = closes.iloc[-1]
        if start_price <= 0:
            return None
        return (end_price - start_price) / start_price

    def _fmt(r):
        if r is None:
            return "N/A"
        sign = "+" if r >= 0 else ""
        return f"{sign}{r*100:.0f}%"

    r1m = _ret(21)
    r1y = _ret(252)
    r3y = _ret(252 * 3)
    r5y = _ret(252 * 5)

    return {
        "1M": _fmt(r1m),
        "1Y": _fmt(r1y),
        "3Y": _fmt(r3y),
        "5Y": _fmt(r5y),
        "_r5y_raw": r5y,
        "_r1m_raw": r1m,
    }


def downsample_for_chart(closes: pd.Series, n_points: int = 60) -> list[float]:
    """Return ~n_points evenly spaced closes for the chart."""
    arr = closes.values
    if len(arr) <= n_points:
        return [round(float(x), 2) for x in arr]
    indices = np.linspace(0, len(arr) - 1, n_points, dtype=int)
    return [round(float(arr[i]), 2) for i in indices]


# ── Step 4: News surge ────────────────────────────────────────────────────────
def fetch_news_counts(ticker: str, company_name: str) -> dict:
    """
    Returns {"prev": int, "curr": int} article counts.
    Uses NewsAPI if key is set, otherwise Google News RSS (free, ~100 articles/ticker).
    """
    if NEWS_API_KEY:
        return _newsapi_counts(ticker, company_name)
    else:
        return _google_news_counts(ticker, company_name)


def _newsapi_counts(ticker: str, company_name: str) -> dict:
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=7)
    prev_start = today - datetime.timedelta(days=14)

    query = f'"{ticker}" OR "{company_name.split()[0]}"'
    base = "https://newsapi.org/v2/everything"
    headers = {"X-Api-Key": NEWS_API_KEY}

    def _count(from_date, to_date):
        try:
            r = requests.get(base, params={
                "q": query,
                "from": str(from_date),
                "to": str(to_date),
                "language": "en",
                "pageSize": 1,
            }, headers=headers, timeout=8)
            data = r.json()
            return data.get("totalResults", 0)
        except Exception:
            return 0

    curr = _count(week_start, today)
    prev = _count(prev_start, week_start)
    return {"prev": max(prev, 1), "curr": curr}


def _google_news_counts(ticker: str, company_name: str) -> dict:
    """
    Count articles from Google News RSS for the current and prior week.
    Returns up to ~100 articles, giving real differentiation across tickers.
    """
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    two_weeks_ago = today - datetime.timedelta(days=14)

    query = f"{ticker} {company_name.split()[0]} stock"
    try:
        resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": "Mozilla/5.0 (signal-screener/1.0)"},
            timeout=8,
        )
        root = ET.fromstring(resp.content)
        curr = prev = 0
        for item in root.iter("item"):
            pd_el = item.find("pubDate")
            if pd_el is None:
                continue
            try:
                # pubDate format: "Thu, 15 May 2026 10:30:00 GMT"
                dt = datetime.datetime.strptime(pd_el.text[:16], "%a, %d %b %Y").date()
                if dt >= week_ago:
                    curr += 1
                elif dt >= two_weeks_ago:
                    prev += 1
            except Exception:
                pass
        return {"prev": prev, "curr": curr}
    except Exception:
        return {"prev": 0, "curr": 0}


# ── Step 5: Score and select ──────────────────────────────────────────────────
def compute_news_index(candidates: list[dict]) -> None:
    """
    Adds news_index (0–100) to each candidate in place.

    Raw score = this-week count × capped surge multiplier.
    Surge is only applied when prior coverage meets the minimum threshold,
    preventing stocks with 1→3 articles from outscoring stocks with 50→80.
    Final index is min-max normalised across all candidates so it is always
    relative — 100 = most-covered this cycle, 0 = least.
    """
    for c in candidates:
        prev = c["news"]["prev"]
        curr = c["news"]["curr"]
        if prev >= NEWS_MIN_PREV:
            surge = min(curr / max(prev, 1), NEWS_MAX_SURGE)
        else:
            surge = 1.0  # no multiplier for thin prior coverage
        c["_news_raw"] = curr * surge

    raw_scores = [c["_news_raw"] for c in candidates]
    lo, hi = min(raw_scores), max(raw_scores)
    for c in candidates:
        if hi > lo:
            c["news_index"] = round((c["_news_raw"] - lo) / (hi - lo) * 100)
        else:
            c["news_index"] = 50
        del c["_news_raw"]


def score_pick(news_index: int, cup_result: dict) -> float:
    """Score = normalised news index × cup confidence weighting."""
    confidence = cup_result.get("confidence", 0) if cup_result.get("detected") else 0
    return (news_index / 100) * (0.4 + 0.6 * confidence)


def select_top_10(candidates: list[dict]) -> list[dict]:
    """Apply sector cap and pick top 10 by score."""
    candidates_sorted = sorted(candidates, key=lambda x: x["_score"], reverse=True)
    sector_counts = {}
    selected = []

    for c in candidates_sorted:
        sector = c["sector"]
        count = sector_counts.get(sector, 0)
        if count >= MAX_PER_SECTOR:
            continue
        sector_counts[sector] = count + 1
        selected.append(c)
        if len(selected) >= TOP_N:
            break

    return selected


# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    print("\n=== Signal Weekly Screener ===\n")

    # 1. Universe
    universe = load_universe()

    # 2. Fundamentals (parallel)
    print(f"\nFetching fundamentals for {len(universe)} tickers...")
    fundamentals = {}

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_fundamentals, row.ticker): row
                   for row in universe.itertuples()}
        for i, future in enumerate(as_completed(futures)):
            row = futures[future]
            result = future.result()
            if result:
                result["sector"] = row.sector
                result["type"] = row.type
                fundamentals[row.ticker] = result
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(universe)} fetched...")

    print(f"  Got fundamentals for {len(fundamentals)} tickers")

    # 2b. Debt filter
    debt_ok = {
        k: v for k, v in fundamentals.items()
        if passes_debt_filter(v.get("debt_equity"), v["type"])
    }
    print(f"  After debt filter: {len(debt_ok)} tickers")

    # 3. Price history + returns + cup & handle
    print(f"\nFetching price history and running pattern detection...")
    cup_candidates = []

    def process_ticker(ticker, meta):
        closes = fetch_price_history(ticker)
        if closes is None:
            return None

        returns = compute_returns(closes)

        # 5Y return filter
        r5y = returns.get("_r5y_raw")
        if r5y is not None and r5y < MIN_5Y_RETURN:
            return None

        # Cup & handle on last ~260 trading days (12 months)
        recent = closes.iloc[-260:] if len(closes) >= 260 else closes
        cup_result = cup_handle.detect(list(recent.values))

        if not cup_result["detected"]:
            return None

        chart_prices = downsample_for_chart(closes.iloc[-260:], n_points=60)

        return {
            "ticker": ticker,
            "type": meta["type"],
            "name": meta.get("short_name", ticker),
            "sector": meta["sector"],
            "price": round(meta["price"], 2),
            "desc": meta.get("desc", ""),
            "debt_equity": meta.get("debt_equity"),
            "returns": {k: v for k, v in returns.items() if not k.startswith("_")},
            "prices": chart_prices,
            "cup": cup_result,
        }

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process_ticker, k, v): k for k, v in debt_ok.items()}
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result:
                cup_candidates.append(result)
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(debt_ok)} processed...")

    print(f"  Cup & handle patterns found: {len(cup_candidates)}")

    if not cup_candidates:
        print("No candidates passed all filters. Exiting.")
        return

    # 4. News counts
    print(f"\nFetching news counts for {len(cup_candidates)} candidates...")
    for c in cup_candidates:
        c["news"] = fetch_news_counts(c["ticker"], c["name"])
        time.sleep(0.1)  # gentle rate limiting

    # 4b. Normalise news into a 0-100 index relative to all candidates
    compute_news_index(cup_candidates)

    # 5. Score and select
    for c in cup_candidates:
        c["_score"] = score_pick(c["news_index"], c["cup"])

    picks = select_top_10(cup_candidates)
    print(f"\nSelected {len(picks)} picks:")
    for p in picks:
        print(f"  {p['ticker']:6s} {p['sector']:30s} score={p['_score']:.2f}")

    # Enrich with display fields
    for p in picks:
        de = p.get("debt_equity")
        if p["type"] == "etf":
            p["debt"] = "N/A (ETF)"
            p["deRating"] = "good"
        elif de is None:
            p["debt"] = "N/A"
            p["deRating"] = "warn"
        else:
            p["debt"] = f"{de:.2f}"
            p["deRating"] = "good" if de <= 0.3 else "warn" if de <= 0.5 else "bad"

        # Why this pick — auto-generated summary
        conf_pct = int(p["cup"]["confidence"] * 100)
        cup_depth = p["cup"].get("cup_depth_pct", "?")
        news_idx = p["news_index"]
        debt_note = "No ETF-level debt." if p["type"] == "etf" else f"D/E ratio of {p['debt']}."
        p["why"] = (
            f"{p['ticker']} formed a {cup_depth}% cup over the past 12 months "
            f"(pattern confidence {conf_pct}%). News coverage index {news_idx}/100 "
            f"relative to all screened candidates this cycle. {debt_note}"
        )

        # Clean up internal fields
        p.pop("_score", None)
        p.pop("debt_equity", None)

    # 6. Render report
    today = datetime.date.today()
    output_path = f"signal_{today.strftime('%Y%m%d')}.html"
    report_module.save(picks, output_path, today)
    print(f"\nDone. Report: {output_path}")


if __name__ == "__main__":
    run()
