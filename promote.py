"""
promote.py
Reads the V2 backtest summary and prints a promotion recommendation.

To promote the challenger to champion: set ACTIVE_CHAMPION = CHALLENGER
in strategies.py. This is intentionally a manual step.

Run: python3 promote.py
"""

import json
import sys


def check_promotion(summary_path: str = "docs/backtest_unified_summary.json") -> None:
    try:
        with open(summary_path) as f:
            s = json.load(f)
    except FileNotFoundError:
        print(f"No backtest summary found at {summary_path}.")
        print("Run the unified backtest first: python3 backtest_unified.py")
        sys.exit(1)

    ch = s["champion"]
    cr = s["challenger"]
    spy = s["spy"]

    print(f"\n=== Promotion Check ({s['start_date']} → {s['end_date']}) ===\n")
    print(f"{'':30s} {'Champion':>12}  {'Challenger':>12}  {'SPY':>10}")
    print(f"{'─'*68}")
    print(f"{'Avg 5-day return':30s} {ch['avg_return']:>+11.2%}  {cr['avg_return']:>+11.2%}  {spy['avg_return']:>+9.2%}")
    print(f"{'Win rate vs SPY':30s} {ch['win_rate']:>11.0%}  {cr['win_rate']:>11.0%}")
    print(f"{'Rolling 12-week avg':30s} {ch['rolling_12w']:>+11.2%}  {cr['rolling_12w']:>+11.2%}  {spy['rolling_12w']:>+9.2%}")
    print(f"{'Reached +5%':30s} {ch['pct_reached_5pct']:>11.0%}  {cr['pct_reached_5pct']:>11.0%}")
    days_ch = f"{ch['avg_days_to_5pct']:.0f}d" if ch['avg_days_to_5pct'] else "—"
    days_cr = f"{cr['avg_days_to_5pct']:.0f}d" if cr['avg_days_to_5pct'] else "—"
    print(f"{'Avg days to +5%':30s} {days_ch:>12}  {days_cr:>12}")
    print()

    cr_excess = cr["avg_return"] - spy["avg_return"]
    ch_excess = ch["avg_return"] - spy["avg_return"]
    cr_win    = cr["win_rate"]

    if cr_excess > ch_excess and cr_win >= 0.55:
        print(f"RECOMMEND PROMOTION: Challenger beats champion and SPY ({cr_excess:+.2%} excess, {cr_win:.0%} win rate).")
        print("To promote: set  ACTIVE_CHAMPION = CHALLENGER  in strategies.py")
    elif cr_excess > 0:
        print(f"Challenger beats SPY ({cr_excess:+.2%}) but win rate {cr_win:.0%} < 55% or trails champion. Continue monitoring.")
    else:
        print(f"Champion holds. Challenger underperforms SPY ({cr_excess:+.2%}).")


if __name__ == "__main__":
    check_promotion()
