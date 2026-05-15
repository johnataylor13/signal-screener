"""
backtest_report.py
Renders the Signal backtest results as a self-contained HTML file.
Buy-and-hold DCA model: $1K/week per strategy, never sold.
"""

import json
from report import _chartjs


def save(weekly_results: list[dict], summary: dict, output_path: str):
    html = render(weekly_results, summary)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Backtest report saved to {output_path}")


def render(weekly_results: list[dict], summary: dict) -> str:
    chartjs = _chartjs()

    # Chart series — dollar portfolio values measured at each week's exit date
    labels     = [str(w["exit_date"])    for w in weekly_results]
    sig_vals   = [w["signal_value"]      for w in weekly_results]
    spy_vals   = [w["spy_value"]         for w in weekly_results]
    sp500_vals = [w["sp500_value"]       for w in weekly_results]
    qqq_vals   = [w["qqq_value"]         for w in weekly_results]
    dep_vals   = [w["total_deployed"]    for w in weekly_results]

    weeks_json = json.dumps([
        {
            "date":     str(w["date"]),
            "exit":     str(w["exit_date"]),
            "sig_val":  w["signal_value"],
            "spy_val":  w["spy_value"],
            "sp5_val":  w["sp500_value"],
            "qqq_val":  w["qqq_value"],
            "deployed": w["total_deployed"],
            "n_cand":   w["n_candidates"],
            "picks": [
                {
                    "ticker": p["ticker"],
                    "sector": p["sector"],
                    "type":   p["type"],
                    "conf":   round(p["confidence"] * 100),
                    "depth":  p["cup_depth_pct"],
                    "entry":  p["entry_price"],
                    "cost":   p.get("cost",   0),
                    "shares": p.get("shares", 0),
                }
                for p in w["picks"]
            ],
        }
        for w in weekly_results
    ])

    # Hero colour: green if Signal beat SPY, red if not
    signal_beats_spy = summary["signal_final"] >= summary["spy_final"]
    signal_color = "#c8f542" if signal_beats_spy else "#ff4d4d"

    def fmt_gain(pct: float) -> str:
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    def fmt_abs(val: float) -> str:
        sign = "+" if val >= 0 else "-"
        return f"{sign}${abs(val):,.0f}"

    signal_abs = summary["signal_final"] - summary["total_deployed"]
    spy_abs    = summary["spy_final"]    - summary["total_deployed"]
    sp500_abs  = summary["sp500_final"]  - summary["total_deployed"]
    qqq_abs    = summary["qqq_final"]    - summary["total_deployed"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal — Backtest</title>
<script>{chartjs}</script>
<style>
  :root {{
    --bg: #0a0a0a; --surface: #111111; --border: #1e1e1e; --border-active: #2e2e2e;
    --text: #e8e8e8; --muted: #555; --accent: #c8f542; --accent-dim: rgba(200,245,66,0.08);
    --red: #ff4d4d; --orange: #f5a623; --blue: #7eb8f7;
    --mono: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--text); font-family:var(--mono); font-size:13px; line-height:1.6; }}

  header {{ padding:32px 20px 24px; border-bottom:1px solid var(--border); }}
  .wordmark {{ font-size:11px; letter-spacing:0.2em; color:var(--muted); text-transform:uppercase; }}
  h1 {{ font-size:22px; font-weight:300; letter-spacing:-0.02em; margin-top:12px; }}
  .subline {{ font-size:11px; color:var(--muted); letter-spacing:0.05em; margin-top:4px; }}

  .hero {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; padding:20px; border-bottom:1px solid var(--border); }}
  @media(max-width:700px) {{ .hero {{ grid-template-columns:1fr 1fr; }} }}
  @media(max-width:400px) {{ .hero {{ grid-template-columns:1fr; }} }}
  .hero-stat {{ background:var(--surface); border:1px solid var(--border); border-radius:2px; padding:18px 16px; }}
  .hero-label {{ font-size:9px; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); margin-bottom:8px; }}
  .hero-value {{ font-size:24px; font-weight:300; letter-spacing:-0.03em; }}
  .hero-sub {{ font-size:10px; color:var(--muted); margin-top:4px; }}

  .section {{ padding:20px; border-bottom:1px solid var(--border); }}
  .section-label {{ font-size:9px; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); margin-bottom:14px; }}

  .stats-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }}
  @media(min-width:600px) {{ .stats-grid {{ grid-template-columns:repeat(4,1fr); }} }}
  .stat {{ background:var(--surface); border:1px solid var(--border); border-radius:2px; padding:14px 12px; }}
  .stat-label {{ font-size:10px; color:var(--muted); margin-bottom:4px; }}
  .stat-value {{ font-size:16px; }}
  .stat-sub {{ font-size:10px; color:var(--muted); margin-top:2px; }}
  .pos {{ color:var(--accent); }} .neg {{ color:var(--red); }} .neu {{ color:var(--text); }}

  .chart-wrap {{ height:260px; position:relative; }}

  .weeks {{ display:flex; flex-direction:column; gap:6px; padding:12px 20px 32px; }}
  .week-card {{ background:var(--surface); border:1px solid var(--border); border-radius:2px; overflow:hidden; }}
  .week-header {{ display:flex; justify-content:space-between; align-items:center; padding:12px 14px; cursor:pointer; user-select:none; gap:8px; }}
  .week-date {{ font-size:12px; }}
  .week-meta {{ font-size:10px; color:var(--muted); }}
  .chevron {{ font-size:10px; color:var(--muted); transition:transform 0.2s; }}
  .week-card.open .chevron {{ transform:rotate(180deg); }}
  .week-body {{ display:none; border-top:1px solid var(--border); overflow-x:auto; }}
  .week-card.open .week-body {{ display:block; }}
  table {{ width:100%; border-collapse:collapse; font-size:11px; }}
  th {{ text-align:left; padding:8px 12px; color:var(--muted); font-weight:400; font-size:9px; letter-spacing:0.1em; text-transform:uppercase; border-bottom:1px solid var(--border); white-space:nowrap; }}
  td {{ padding:9px 12px; border-bottom:1px solid var(--border); white-space:nowrap; }}
  tr:last-child td {{ border-bottom:none; }}
  .badge {{ font-size:9px; letter-spacing:0.1em; text-transform:uppercase; padding:2px 5px; border-radius:1px; border:1px solid; }}
  .badge-etf {{ color:var(--blue); border-color:rgba(126,184,247,0.3); }}
  .badge-stock {{ color:var(--muted); border-color:var(--border-active); }}

  .methodology {{ margin:0 20px 32px; padding:14px; background:var(--surface); border:1px solid var(--border); border-radius:2px; font-size:11px; color:var(--muted); font-family:var(--sans); line-height:1.7; }}
  .methodology strong {{ color:#888; }}

  footer {{ padding:20px; border-top:1px solid var(--border); font-size:10px; color:#333; display:flex; justify-content:space-between; }}
  footer a {{ color:#444; text-decoration:none; }}
  footer a:hover {{ color:var(--muted); }}
</style>
</head>
<body>

<header>
  <div class="wordmark">Signal</div>
  <h1>Backtest — 52 Weeks</h1>
  <div class="subline">{summary['start_date']} → {summary['end_date']} · $1,000/week DCA · buy &amp; hold · never sold</div>
</header>

<div class="hero">
  <div class="hero-stat">
    <div class="hero-label">Signal Portfolio</div>
    <div class="hero-value" style="color:{signal_color}">${summary['signal_final']:,.0f}</div>
    <div class="hero-sub">{fmt_gain(summary['signal_gain_pct'])} · {fmt_abs(signal_abs)} gain on ${summary['total_deployed']:,.0f} deployed</div>
  </div>
  <div class="hero-stat">
    <div class="hero-label">SPY (Benchmark)</div>
    <div class="hero-value" style="color:var(--blue)">${summary['spy_final']:,.0f}</div>
    <div class="hero-sub">{fmt_gain(summary['spy_gain_pct'])} · {fmt_abs(spy_abs)} · same capital</div>
  </div>
  <div class="hero-stat">
    <div class="hero-label">S&amp;P 500 Index</div>
    <div class="hero-value" style="color:var(--orange)">${summary['sp500_final']:,.0f}</div>
    <div class="hero-sub">{fmt_gain(summary['sp500_gain_pct'])} · {fmt_abs(sp500_abs)} · same capital</div>
  </div>
  <div class="hero-stat">
    <div class="hero-label">QQQ (Nasdaq-100)</div>
    <div class="hero-value" style="color:#b07ef5">${summary['qqq_final']:,.0f}</div>
    <div class="hero-sub">{fmt_gain(summary['qqq_gain_pct'])} · {fmt_abs(qqq_abs)} · same capital</div>
  </div>
</div>

<div class="section">
  <div class="section-label">Portfolio Value Over Time</div>
  <div class="chart-wrap">
    <canvas id="cumChart"></canvas>
  </div>
</div>

<div class="section">
  <div class="section-label">Summary</div>
  <div class="stats-grid">
    <div class="stat">
      <div class="stat-label">Total Deployed</div>
      <div class="stat-value neu">${summary['total_deployed']:,.0f}</div>
      <div class="stat-sub">${summary['weekly_invest']:,.0f}/week × {summary['weeks']} weeks</div>
    </div>
    <div class="stat">
      <div class="stat-label">Signal Gain</div>
      <div class="stat-value {'pos' if summary['signal_gain_pct'] >= 0 else 'neg'}">{fmt_gain(summary['signal_gain_pct'])}</div>
      <div class="stat-sub">{fmt_abs(signal_abs)} absolute</div>
    </div>
    <div class="stat">
      <div class="stat-label">SPY Gain</div>
      <div class="stat-value {'pos' if summary['spy_gain_pct'] >= 0 else 'neg'}">{fmt_gain(summary['spy_gain_pct'])}</div>
      <div class="stat-sub">{fmt_abs(spy_abs)} absolute</div>
    </div>
    <div class="stat">
      <div class="stat-label">Weeks Signal &gt; SPY</div>
      <div class="stat-value {'pos' if summary['win_rate_vs_spy'] >= 50 else 'neg'}">{summary['win_rate_vs_spy']:.0f}%</div>
      <div class="stat-sub">by portfolio value</div>
    </div>
  </div>
</div>

<div style="padding:16px 20px 8px">
  <div style="font-size:9px;letter-spacing:0.18em;text-transform:uppercase;color:var(--muted)">Weekly Picks Detail</div>
</div>
<div class="weeks" id="weeks"></div>

<div class="methodology">
  <strong>Methodology &amp; limitations.</strong>
  Each week $1,000 is deployed equally across the Signal picks and held permanently — no selling occurs.
  SPY and S&amp;P 500 receive the same $1,000/week for an apples-to-apples DCA comparison.
  Scoring uses cup &amp; handle confidence only — news surge is excluded because no free historical news API exists.
  Debt/equity ratios use <em>current</em> values (not historical), introducing mild look-ahead bias.
  Universe uses the current S&amp;P 500 constituent list, creating mild survivorship bias.
  Transaction costs and slippage are not modelled.
  Entry = Wednesday close. Portfolio valued = following Wednesday close.
  This is not investment advice.
</div>

<footer>
  <a href="index.html">← Archive</a>
  <span>Signal Backtest · not investment advice</span>
</footer>

<script>
const weeks = {weeks_json};
const labels     = {json.dumps(labels)};
const sigVals    = {json.dumps(sig_vals)};
const spyVals    = {json.dumps(spy_vals)};
const sp500Vals  = {json.dumps(sp500_vals)};
const qqqVals    = {json.dumps(qqq_vals)};
const depVals    = {json.dumps(dep_vals)};

// ── Portfolio value chart ──
new Chart(document.getElementById('cumChart'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{
        label: 'Signal',
        data: sigVals,
        borderColor: '#c8f542',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      }},
      {{
        label: 'SPY',
        data: spyVals,
        borderColor: '#7eb8f7',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        borderDash: [5, 3],
        fill: false,
      }},
      {{
        label: 'S&P 500',
        data: sp500Vals,
        borderColor: '#f5a623',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        borderDash: [2, 4],
        fill: false,
      }},
      {{
        label: 'QQQ',
        data: qqqVals,
        borderColor: '#b07ef5',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        borderDash: [6, 2],
        fill: false,
      }},
      {{
        label: 'Cost Basis',
        data: depVals,
        borderColor: '#333',
        borderWidth: 1,
        pointRadius: 0,
        tension: 0,
        borderDash: [1, 5],
        fill: false,
      }},
    ],
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ labels: {{ color: '#555', font: {{ family: 'ui-monospace', size: 10 }} }} }},
      tooltip: {{
        backgroundColor: '#111', borderColor: '#222', borderWidth: 1,
        titleColor: '#555', bodyColor: '#e8e8e8',
        titleFont: {{ family: 'ui-monospace', size: 10 }},
        bodyFont:  {{ family: 'ui-monospace', size: 11 }},
        callbacks: {{
          label: ctx => ' ' + ctx.dataset.label + ': $' +
            ctx.parsed.y.toLocaleString('en-US', {{minimumFractionDigits: 0, maximumFractionDigits: 0}}),
        }},
      }},
    }},
    scales: {{
      x: {{ display: false }},
      y: {{
        grid: {{ color: 'rgba(255,255,255,0.03)' }},
        ticks: {{
          color: '#333',
          font: {{ family: 'ui-monospace', size: 9 }},
          callback: v => '$' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v),
        }},
        border: {{ display: false }},
      }},
    }},
  }},
}});

// ── Weekly picks table ──
const container = document.getElementById('weeks');
weeks.slice().reverse().forEach(w => {{
  const card = document.createElement('div');
  card.className = 'week-card';

  const picksBody = w.picks.length === 0
    ? '<div style="padding:12px 14px;color:var(--muted);font-size:11px">No cup &amp; handle patterns detected this week.</div>'
    : '<table><thead><tr>' +
        '<th>Ticker</th><th>Type</th><th>Sector</th>' +
        '<th>Conf</th><th>Cup depth</th>' +
        '<th>Entry</th><th>Shares</th><th>Invested</th>' +
      '</tr></thead><tbody>' +
      w.picks.map(p =>
        '<tr>' +
          '<td><b>' + p.ticker + '</b></td>' +
          '<td><span class="badge badge-' + p.type + '">' + p.type.toUpperCase() + '</span></td>' +
          '<td style="color:var(--muted)">' + p.sector + '</td>' +
          '<td style="color:var(--muted)">' + p.conf + '%</td>' +
          '<td style="color:var(--muted)">' + p.depth + '%</td>' +
          '<td>$' + p.entry.toFixed(2) + '</td>' +
          '<td style="color:var(--muted)">' + p.shares.toFixed(4) + '</td>' +
          '<td>$' + p.cost.toFixed(2) + '</td>' +
        '</tr>'
      ).join('') +
      '</tbody></table>';

  const sigFmt = '$' + w.sig_val.toLocaleString('en-US', {{maximumFractionDigits: 0}});
  const depFmt = '$' + w.deployed.toLocaleString('en-US', {{maximumFractionDigits: 0}});

  card.innerHTML =
    '<div class="week-header">' +
      '<div>' +
        '<div class="week-date">' + w.date + '</div>' +
        '<div class="week-meta">' + w.picks.length + ' picks · ' + w.n_cand + ' candidates</div>' +
      '</div>' +
      '<div style="text-align:right">' +
        '<div class="week-meta">Signal <span style="color:var(--text)">' + sigFmt + '</span></div>' +
        '<div class="week-meta">Deployed ' + depFmt + '</div>' +
      '</div>' +
      '<div class="chevron">▼</div>' +
    '</div>' +
    '<div class="week-body">' + picksBody + '</div>';

  card.querySelector('.week-header').addEventListener('click', () => card.classList.toggle('open'));
  container.appendChild(card);
}});
</script>
</body>
</html>"""
