"""
backtest_report.py
Renders the Signal backtest results as a self-contained HTML file.
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

    # Chart data
    labels       = [str(w["date"]) for w in weekly_results]
    signal_cum   = [w["portfolio_cumulative"] for w in weekly_results]
    spy_cum      = [w["spy_cumulative"]       for w in weekly_results]
    weekly_bars  = [round(w["portfolio_return"] * 100, 2) for w in weekly_results]

    # Picks table rows (one collapsible section per week)
    weeks_json = json.dumps([
        {
            "date":      str(w["date"]),
            "exit_date": str(w["exit_date"]),
            "port_ret":  round(w["portfolio_return"] * 100, 2),
            "spy_ret":   round(w["spy_return"]       * 100, 2),
            "n_cand":    w["n_candidates"],
            "picks": [
                {
                    "ticker":   p["ticker"],
                    "sector":   p["sector"],
                    "type":     p["type"],
                    "conf":     round(p["confidence"] * 100),
                    "depth":    p["cup_depth_pct"],
                    "entry":    p["entry_price"],
                    "exit":     p["exit_price"],
                    "ret":      round(p["weekly_return"] * 100, 2),
                }
                for p in w["picks"]
            ],
        }
        for w in weekly_results
    ])

    # Hero colour
    outperformed = summary["total_return"] >= summary["spy_total_return"]
    hero_color   = "#c8f542" if outperformed else "#ff4d4d"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal — Backtest</title>
<script>{chartjs}</script>
<style>
  :root {{
    --bg: #0a0a0a;
    --surface: #111111;
    --border: #1e1e1e;
    --border-active: #2e2e2e;
    --text: #e8e8e8;
    --muted: #555;
    --accent: #c8f542;
    --accent-dim: rgba(200,245,66,0.08);
    --red: #ff4d4d;
    --orange: #f5a623;
    --mono: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--text); font-family:var(--mono); font-size:13px; line-height:1.6; }}

  header {{ padding:32px 20px 24px; border-bottom:1px solid var(--border); }}
  .wordmark {{ font-size:11px; letter-spacing:0.2em; color:var(--muted); text-transform:uppercase; }}
  h1 {{ font-size:22px; font-weight:300; letter-spacing:-0.02em; margin-top:12px; }}
  .subline {{ font-size:11px; color:var(--muted); letter-spacing:0.05em; margin-top:4px; }}

  .hero {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; padding:20px; border-bottom:1px solid var(--border); }}
  .hero-stat {{ background:var(--surface); border:1px solid var(--border); border-radius:2px; padding:18px 16px; }}
  .hero-label {{ font-size:9px; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); margin-bottom:8px; }}
  .hero-value {{ font-size:28px; font-weight:300; letter-spacing:-0.03em; }}
  .hero-sub {{ font-size:10px; color:var(--muted); margin-top:4px; }}

  .section {{ padding:20px; border-bottom:1px solid var(--border); }}
  .section-label {{ font-size:9px; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); margin-bottom:14px; }}

  .stats-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }}
  @media(min-width:600px) {{ .stats-grid {{ grid-template-columns:repeat(4,1fr); }} }}
  .stat {{ background:var(--surface); border:1px solid var(--border); border-radius:2px; padding:14px 12px; }}
  .stat-label {{ font-size:10px; color:var(--muted); margin-bottom:4px; }}
  .stat-value {{ font-size:16px; }}
  .pos {{ color:var(--accent); }}
  .neg {{ color:var(--red); }}
  .neu {{ color:var(--text); }}

  .chart-wrap {{ height:220px; position:relative; }}

  .weeks {{ display:flex; flex-direction:column; gap:6px; padding:12px 20px 32px; }}
  .week-card {{ background:var(--surface); border:1px solid var(--border); border-radius:2px; overflow:hidden; }}
  .week-header {{ display:flex; justify-content:space-between; align-items:center; padding:12px 14px; cursor:pointer; user-select:none; gap:8px; }}
  .week-date {{ font-size:12px; }}
  .week-ret {{ font-size:12px; }}
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
  .badge-etf {{ color:#7eb8f7; border-color:rgba(126,184,247,0.3); }}
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
  <div class="subline">{summary['start_date']} → {summary['end_date']} · equal-weight · 1-week hold</div>
</header>

<div class="hero">
  <div class="hero-stat">
    <div class="hero-label">Signal Total Return</div>
    <div class="hero-value" style="color:{hero_color}">{summary['total_return']:+.1f}%</div>
    <div class="hero-sub">{summary['weeks']} weeks simulated</div>
  </div>
  <div class="hero-stat">
    <div class="hero-label">SPY Benchmark</div>
    <div class="hero-value" style="color:var(--muted)">{summary['spy_total_return']:+.1f}%</div>
    <div class="hero-sub">same period</div>
  </div>
</div>

<div class="section">
  <div class="section-label">Cumulative Return</div>
  <div class="chart-wrap">
    <canvas id="cumChart"></canvas>
  </div>
</div>

<div class="section">
  <div class="section-label">Weekly Portfolio Return</div>
  <div class="chart-wrap">
    <canvas id="barChart"></canvas>
  </div>
</div>

<div class="section">
  <div class="section-label">Summary</div>
  <div class="stats-grid">
    <div class="stat">
      <div class="stat-label">Win Rate vs SPY</div>
      <div class="stat-value {'pos' if summary['win_rate_vs_spy'] >= 50 else 'neg'}">{summary['win_rate_vs_spy']:.0f}%</div>
    </div>
    <div class="stat">
      <div class="stat-label">Avg Weekly Return</div>
      <div class="stat-value {'pos' if summary['avg_weekly_return'] >= 0 else 'neg'}">{summary['avg_weekly_return']:+.2f}%</div>
    </div>
    <div class="stat">
      <div class="stat-label">Best Week</div>
      <div class="stat-value pos">{summary['best_week_return']:+.1f}%</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px">{summary['best_week_date']}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Worst Week</div>
      <div class="stat-value neg">{summary['worst_week_return']:+.1f}%</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px">{summary['worst_week_date']}</div>
    </div>
  </div>
</div>

<div style="padding:16px 20px 8px">
  <div style="font-size:9px;letter-spacing:0.18em;text-transform:uppercase;color:var(--muted)">Weekly Picks Detail</div>
</div>
<div class="weeks" id="weeks"></div>

<div class="methodology">
  <strong>Methodology &amp; limitations.</strong>
  Scoring uses cup &amp; handle confidence only — news surge is excluded because no free historical news API exists.
  Debt/equity ratios use <em>current</em> values (not historical), introducing mild look-ahead bias.
  Universe uses the current S&amp;P 500 list, creating mild survivorship bias.
  Transaction costs and slippage are not modelled.
  Entry = Wednesday close. Exit = following Wednesday close.
  This is not investment advice.
</div>

<footer>
  <a href="index.html">← Archive</a>
  <span>Signal Backtest · not investment advice</span>
</footer>

<script>
const weeks = {weeks_json};
const labels = {json.dumps(labels)};
const signalCum = {json.dumps(signal_cum)};
const spyCum = {json.dumps(spy_cum)};
const weeklyBars = {json.dumps(weekly_bars)};

// ── Cumulative return chart ──
new Chart(document.getElementById('cumChart'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{
        label: 'Signal',
        data: signalCum,
        borderColor: '#c8f542',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: {{ target: 'origin', above: 'rgba(200,245,66,0.05)' }},
      }},
      {{
        label: 'SPY',
        data: spyCum,
        borderColor: '#444',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        borderDash: [4, 3],
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
        callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y > 0 ? '+' : ''}}${{ctx.parsed.y.toFixed(2)}}%` }},
      }},
    }},
    scales: {{
      x: {{ display: false }},
      y: {{
        grid: {{ color: 'rgba(255,255,255,0.03)' }},
        ticks: {{ color: '#333', font: {{ family: 'ui-monospace', size: 9 }}, callback: v => v + '%' }},
        border: {{ display: false }},
      }},
    }},
  }},
}});

// ── Weekly bar chart ──
new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [{{
      data: weeklyBars,
      backgroundColor: weeklyBars.map(v => v >= 0 ? 'rgba(200,245,66,0.6)' : 'rgba(255,77,77,0.6)'),
      borderWidth: 0,
    }}],
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: '#111', borderColor: '#222', borderWidth: 1,
        titleColor: '#555', bodyColor: '#e8e8e8',
        titleFont: {{ family: 'ui-monospace', size: 10 }},
        bodyFont:  {{ family: 'ui-monospace', size: 11 }},
        callbacks: {{ label: ctx => ` ${{ctx.parsed.y > 0 ? '+' : ''}}${{ctx.parsed.y.toFixed(2)}}%` }},
      }},
    }},
    scales: {{
      x: {{ display: false }},
      y: {{
        grid: {{ color: 'rgba(255,255,255,0.03)' }},
        ticks: {{ color: '#333', font: {{ family: 'ui-monospace', size: 9 }}, callback: v => v + '%' }},
        border: {{ display: false }},
      }},
    }},
  }},
}});

// ── Weekly picks table ──
const container = document.getElementById('weeks');
weeks.slice().reverse().forEach(w => {{
  const portCls = w.port_ret >= 0 ? 'pos' : 'neg';
  const spyCls  = w.spy_ret  >= 0 ? 'pos' : 'neg';
  const vs = w.port_ret - w.spy_ret;
  const vsCls = vs >= 0 ? 'pos' : 'neg';

  const card = document.createElement('div');
  card.className = 'week-card';
  card.innerHTML = `
    <div class="week-header">
      <div>
        <div class="week-date">${{w.date}}</div>
        <div class="week-meta">${{w.picks.length}} picks · ${{w.n_cand}} candidates</div>
      </div>
      <div style="text-align:right">
        <div class="week-ret ${{portCls}}">${{w.port_ret > 0 ? '+' : ''}}<b>${{w.port_ret.toFixed(2)}}%</b></div>
        <div class="week-meta">vs SPY <span class="${{vsCls}}">${{vs > 0 ? '+' : ''}}<b>${{vs.toFixed(2)}}%</b></span></div>
      </div>
      <div class="chevron">▼</div>
    </div>
    <div class="week-body">
      <table>
        <thead>
          <tr>
            <th>Ticker</th><th>Type</th><th>Sector</th>
            <th>Conf</th><th>Cup depth</th>
            <th>Entry</th><th>Exit</th><th>Return</th>
          </tr>
        </thead>
        <tbody>
          ${{w.picks.map(p => `
          <tr>
            <td><b>${{p.ticker}}</b></td>
            <td><span class="badge badge-${{p.type}}">${{p.type.toUpperCase()}}</span></td>
            <td style="color:var(--muted)">${{p.sector}}</td>
            <td style="color:var(--muted)">${{p.conf}}%</td>
            <td style="color:var(--muted)">${{p.depth}}%</td>
            <td>$${{p.entry.toFixed(2)}}</td>
            <td>$${{p.exit.toFixed(2)}}</td>
            <td class="${{p.ret >= 0 ? 'pos' : 'neg'}}">${{p.ret > 0 ? '+' : ''}}<b>${{p.ret.toFixed(2)}}%</b></td>
          </tr>`).join('')}}
        </tbody>
      </table>
    </div>
  `;
  card.querySelector('.week-header').addEventListener('click', () => card.classList.toggle('open'));
  container.appendChild(card);
}});
</script>
</body>
</html>"""
