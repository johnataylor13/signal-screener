"""
backtest_report_unified.py
Renders the unified champion-vs-challenger backtest as self-contained HTML.
"""

import json
from report import _chartjs


def save(weekly_results: list[dict], summary: dict, output_path: str) -> None:
    html = render(weekly_results, summary)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Unified backtest report saved to {output_path}")


def _fmtp(v: float) -> str:
    return f"{'+'if v>=0 else ''}{v*100:.2f}%"

def _fmtdays(v) -> str:
    return f"{v:.0f}" if v is not None else "—"


def render(weekly_results: list[dict], summary: dict) -> str:
    chartjs = _chartjs()
    ch  = summary["champion"]
    cr  = summary["challenger"]
    spy = summary["spy"]

    labels     = [str(w["entry_date"])          for w in weekly_results]
    champ_rets = [round(w["champion_return"]  * 100, 2) for w in weekly_results]
    chall_rets = [round(w["challenger_return"] * 100, 2) for w in weekly_results]
    spy_rets   = [round(w["spy_return"]        * 100, 2) for w in weekly_results]

    weeks_json = json.dumps([
        {
            "entry":       str(w["entry_date"]),
            "exit":        str(w["exit_date"]),
            "champ_ret":   round(w["champion_return"]  * 100, 2),
            "chall_ret":   round(w["challenger_return"] * 100, 2),
            "spy_ret":     round(w["spy_return"]        * 100, 2),
            "champ_beat":  w["champion_beat_spy"],
            "chall_beat":  w["challenger_beat_spy"],
            "n_champ_cand":w["n_champion_cand"],
            "n_chall_cand":w["n_challenger_cand"],
            "champ_picks": [
                {
                    "ticker":    p["ticker"],
                    "sector":    p["sector"],
                    "type":      p["type"],
                    "score":     round(p.get("confidence", p.get("composite", 0)), 3),
                    "entry":     p["entry_price"],
                    "exit":      p["exit_price"],
                    "pnl":       round(p["pnl_pct"] * 100, 2),
                    "days5":     p["days_to_5pct"],
                    "reached5":  p["reached_5pct"],
                    "trunc5":    p["truncated_5pct"],
                }
                for p in w["champion_picks"]
            ],
            "chall_picks": [
                {
                    "ticker":    p["ticker"],
                    "sector":    p["sector"],
                    "type":      p["type"],
                    "score":     round(p.get("composite", 0), 3),
                    "rsi":       p.get("rsi", "—"),
                    "roc5":      round(p.get("roc5", 0) * 100, 1),
                    "vsurge":    p.get("volume_surge", "—"),
                    "entry":     p["entry_price"],
                    "exit":      p["exit_price"],
                    "pnl":       round(p["pnl_pct"] * 100, 2),
                    "days5":     p["days_to_5pct"],
                    "reached5":  p["reached_5pct"],
                    "trunc5":    p["truncated_5pct"],
                }
                for p in w["challenger_picks"]
            ],
        }
        for w in weekly_results
    ], default=str)

    ch_color  = "#c8f542" if ch["avg_return"]  >= spy["avg_return"] else "#f5a623"
    cr_color  = "#c8f542" if cr["avg_return"]  >= spy["avg_return"] else "#f5a623"

    ch_days  = _fmtdays(ch["avg_days_to_5pct"])
    cr_days  = _fmtdays(cr["avg_days_to_5pct"])
    cap_days = summary["five_pct_cap_days"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Signal — Unified Backtest</title>
<script>{chartjs}</script>
<style>
  :root{{
    --bg:#0a0a0a;--surface:#111;--border:#1e1e1e;--border-active:#2e2e2e;
    --text:#e8e8e8;--muted:#555;--accent:#c8f542;--accent-dim:rgba(200,245,66,.08);
    --red:#ff4d4d;--orange:#f5a623;--blue:#7eb8f7;
    --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{background:var(--bg);color:var(--text);font-family:var(--mono);font-size:13px;line-height:1.6;}}
  header{{padding:32px 20px 24px;border-bottom:1px solid var(--border);}}
  .wordmark{{font-size:11px;letter-spacing:.2em;color:var(--muted);text-transform:uppercase;}}
  h1{{font-size:22px;font-weight:300;letter-spacing:-.02em;margin-top:12px;}}
  .subline{{font-size:11px;color:var(--muted);letter-spacing:.05em;margin-top:4px;}}

  /* Two-column comparison layout */
  .compare{{display:grid;grid-template-columns:1fr 1fr;gap:0;border-bottom:1px solid var(--border);}}
  .compare-col{{padding:20px;border-right:1px solid var(--border);}}
  .compare-col:last-child{{border-right:none;}}
  .col-label{{font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:14px;}}
  .stat-row{{display:flex;justify-content:space-between;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--border);}}
  .stat-row:last-child{{border-bottom:none;}}
  .stat-name{{font-size:11px;color:var(--muted);}}
  .stat-val{{font-size:13px;}}

  .five-pct{{display:grid;grid-template-columns:1fr 1fr;gap:0;border-bottom:1px solid var(--border);}}
  .five-col{{padding:20px;border-right:1px solid var(--border);}}
  .five-col:last-child{{border-right:none;}}
  .five-header{{font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:14px;}}
  .five-hero{{font-size:28px;font-weight:300;letter-spacing:-.03em;margin-bottom:4px;}}
  .five-sub{{font-size:11px;color:var(--muted);}}
  .five-stats{{margin-top:14px;display:flex;flex-direction:column;gap:6px;}}
  .five-stat-row{{display:flex;justify-content:space-between;font-size:11px;}}
  .five-stat-label{{color:var(--muted);}}

  .section{{padding:20px;border-bottom:1px solid var(--border);}}
  .section-label{{font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:14px;}}
  .chart-wrap{{height:280px;position:relative;}}

  .weeks{{display:flex;flex-direction:column;gap:6px;padding:12px 20px 32px;}}
  .week-card{{background:var(--surface);border:1px solid var(--border);border-radius:2px;overflow:hidden;}}
  .week-header{{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;cursor:pointer;user-select:none;gap:8px;flex-wrap:wrap;}}
  .week-date{{font-size:12px;}}
  .week-returns{{display:flex;gap:16px;font-size:10px;}}
  .chevron{{font-size:10px;color:var(--muted);transition:transform .2s;flex-shrink:0;}}
  .week-card.open .chevron{{transform:rotate(180deg);}}
  .week-body{{display:none;border-top:1px solid var(--border);}}
  .week-card.open .week-body{{display:block;}}
  .picks-grid{{display:grid;grid-template-columns:1fr 1fr;}}
  .picks-section{{padding:10px 14px;border-right:1px solid var(--border);}}
  .picks-section:last-child{{border-right:none;}}
  .picks-label{{font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);margin-bottom:8px;}}
  table{{width:100%;border-collapse:collapse;font-size:11px;}}
  th{{text-align:left;padding:6px 8px;color:var(--muted);font-weight:400;font-size:9px;letter-spacing:.1em;text-transform:uppercase;border-bottom:1px solid var(--border);white-space:nowrap;}}
  td{{padding:7px 8px;border-bottom:1px solid var(--border);white-space:nowrap;}}
  tr:last-child td{{border-bottom:none;}}
  .badge{{font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:2px 5px;border-radius:1px;border:1px solid;}}
  .badge-etf{{color:var(--blue);border-color:rgba(126,184,247,.3);}}
  .badge-stock{{color:var(--muted);border-color:var(--border-active);}}
  .days-reached{{color:var(--accent);}}
  .days-not{{color:var(--muted);}}
  .days-trunc{{color:#333;font-style:italic;}}

  .pos{{color:var(--accent);}} .neg{{color:var(--red);}} .neu{{color:var(--text);}} .ora{{color:var(--orange);}}

  .methodology{{margin:0 20px 32px;padding:14px;background:var(--surface);border:1px solid var(--border);border-radius:2px;font-size:11px;color:var(--muted);font-family:var(--sans);line-height:1.7;}}
  .methodology strong{{color:#888;}}
  footer{{padding:20px;border-top:1px solid var(--border);font-size:10px;color:#333;display:flex;justify-content:space-between;}}

  @media(max-width:600px){{
    .compare,.five-pct{{grid-template-columns:1fr;}}
    .compare-col,.five-col{{border-right:none;border-bottom:1px solid var(--border);}}
    .picks-grid{{grid-template-columns:1fr;}}
    .picks-section{{border-right:none;border-bottom:1px solid var(--border);}}
  }}
</style>
</head>
<body>

<header>
  <div class="wordmark">Signal Screener</div>
  <h1>Unified Backtest — Champion vs Challenger</h1>
  <div class="subline">5-day holds · {summary['weeks']} weeks · {summary['start_date']} → {summary['end_date']}</div>
</header>

<!-- Side-by-side stats -->
<div class="compare">
  <div class="compare-col">
    <div class="col-label">Champion — V1 Cup &amp; Handle</div>
    <div class="stat-row"><span class="stat-name">Avg 5-day return</span><span class="stat-val" style="color:{ch_color}">{_fmtp(ch['avg_return'])}</span></div>
    <div class="stat-row"><span class="stat-name">Win rate vs SPY</span><span class="stat-val">{ch['win_rate']:.0%}</span></div>
    <div class="stat-row"><span class="stat-name">Rolling 12-week avg</span><span class="stat-val">{_fmtp(ch['rolling_12w'])}</span></div>
    <div class="stat-row"><span class="stat-name">Best week</span><span class="stat-val pos">{_fmtp(ch['best_week'])}</span></div>
    <div class="stat-row"><span class="stat-name">Worst week</span><span class="stat-val neg">{_fmtp(ch['worst_week'])}</span></div>
  </div>
  <div class="compare-col">
    <div class="col-label">Challenger — V2 Momentum</div>
    <div class="stat-row"><span class="stat-name">Avg 5-day return</span><span class="stat-val" style="color:{cr_color}">{_fmtp(cr['avg_return'])}</span></div>
    <div class="stat-row"><span class="stat-name">Win rate vs SPY</span><span class="stat-val">{cr['win_rate']:.0%}</span></div>
    <div class="stat-row"><span class="stat-name">Rolling 12-week avg</span><span class="stat-val">{_fmtp(cr['rolling_12w'])}</span></div>
    <div class="stat-row"><span class="stat-name">Best week</span><span class="stat-val pos">{_fmtp(cr['best_week'])}</span></div>
    <div class="stat-row"><span class="stat-name">Worst week</span><span class="stat-val neg">{_fmtp(cr['worst_week'])}</span></div>
  </div>
</div>

<!-- Days to +5% section -->
<div class="five-pct">
  <div class="five-col">
    <div class="five-header">Champion — days to +5%</div>
    <div class="five-hero {'pos' if ch['avg_days_to_5pct'] else 'muted'}">{ch_days} days</div>
    <div class="five-sub">avg for picks that reached +5%</div>
    <div class="five-stats">
      <div class="five-stat-row"><span class="five-stat-label">Reached +5%</span><span>{ch['pct_reached_5pct']:.0%} &nbsp;({ch['reached_5pct_n']} picks)</span></div>
      <div class="five-stat-row"><span class="five-stat-label">Did not reach</span><span>{ch['not_reached_5pct_n']} picks</span></div>
      <div class="five-stat-row"><span class="five-stat-label">Excluded (truncated window)</span><span class="days-trunc">{ch['truncated_5pct_n']} picks</span></div>
      <div class="five-stat-row"><span class="five-stat-label">Cap</span><span>{cap_days} trading days</span></div>
    </div>
  </div>
  <div class="five-col">
    <div class="five-header">Challenger — days to +5%</div>
    <div class="five-hero {'pos' if cr['avg_days_to_5pct'] else 'muted'}">{cr_days} days</div>
    <div class="five-sub">avg for picks that reached +5%</div>
    <div class="five-stats">
      <div class="five-stat-row"><span class="five-stat-label">Reached +5%</span><span>{cr['pct_reached_5pct']:.0%} &nbsp;({cr['reached_5pct_n']} picks)</span></div>
      <div class="five-stat-row"><span class="five-stat-label">Did not reach</span><span>{cr['not_reached_5pct_n']} picks</span></div>
      <div class="five-stat-row"><span class="five-stat-label">Excluded (truncated window)</span><span class="days-trunc">{cr['truncated_5pct_n']} picks</span></div>
      <div class="five-stat-row"><span class="five-stat-label">Cap</span><span>{cap_days} trading days</span></div>
    </div>
  </div>
</div>

<!-- Chart -->
<div class="section">
  <div class="section-label">Weekly 5-day returns — Champion vs Challenger vs SPY</div>
  <div class="chart-wrap"><canvas id="chart"></canvas></div>
</div>

<!-- Per-week cards -->
<div class="weeks" id="weeks-list"></div>

<div class="methodology">
  <strong>Methodology:</strong> Both strategies screened the same universe (S&amp;P 500 + 25 ETFs, D/E ≤ 0.5)
  on identical weekly entry dates. Signals computed on data visible at entry only — no lookahead.
  $1,000 deployed equally across top-10 sector-capped picks each Wednesday; closed following Wednesday.
  <br><br>
  <strong>Champion signal:</strong> cup &amp; handle confidence score (cup_confidence). Note: the live
  V1 formula multiplies by a news index — news is excluded here because no historical free API exists.
  This backtest tests cup_confidence as a standalone short-term predictor.
  <br><br>
  <strong>Challenger signal:</strong> 0.30×ROC(5d) + 0.20×ROC(10d) + 0.25×volume surge + 0.25×EMA alignment.
  Gates: 3/6/12-month returns all positive, RSI 45–70, price &gt; EMA(20), ATR &gt; 0.3%.
  <br><br>
  <strong>Days to +5%:</strong> Forward scan from entry close until price ≥ entry × 1.05.
  Cap: {cap_days} trading days. Picks where fewer than {cap_days} days of forward data exist
  (near end of simulation) are excluded from both the % and average calculations.
  <br><br>
  <strong>Limitations:</strong> Survivorship bias (current S&amp;P 500 list). D/E uses current values.
  No transaction costs or slippage. Past performance does not predict future results.
</div>

<footer>
  <span>Signal Screener — Unified Backtest</span>
  <span>SPY avg: {_fmtp(spy['avg_return'])} · {summary['start_date']} – {summary['end_date']}</span>
</footer>

<script>
const WEEKS = {weeks_json};
const labels     = {json.dumps(labels)};
const champRets  = {json.dumps(champ_rets)};
const challRets  = {json.dumps(chall_rets)};
const spyRets    = {json.dumps(spy_rets)};

new Chart(document.getElementById('chart'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [
      {{
        label: 'Champion',
        data: champRets,
        backgroundColor: champRets.map(v => v >= 0 ? 'rgba(200,245,66,0.6)' : 'rgba(255,77,77,0.6)'),
        borderWidth: 0,
      }},
      {{
        label: 'Challenger',
        data: challRets,
        backgroundColor: challRets.map(v => v >= 0 ? 'rgba(245,166,35,0.6)' : 'rgba(255,77,77,0.4)'),
        borderWidth: 0,
      }},
      {{
        label: 'SPY',
        data: spyRets,
        backgroundColor: 'rgba(126,184,247,0.3)',
        borderWidth: 0,
      }},
    ],
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ labels: {{ color: '#888', font: {{ family: 'ui-monospace', size: 10 }} }} }},
      tooltip: {{
        backgroundColor: '#1a1a1a', borderColor: '#2e2e2e', borderWidth: 1,
        titleColor: '#888', bodyColor: '#e8e8e8',
        callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.raw >= 0 ? '+' : ''}}${{ctx.raw.toFixed(2)}}%` }},
      }},
    }},
    scales: {{
      x: {{ ticks: {{ display: false }}, grid: {{ color: '#1a1a1a' }} }},
      y: {{
        grid: {{ color: '#1a1a1a' }},
        ticks: {{ color: '#555', font: {{ family: 'ui-monospace', size: 10 }}, callback: v => v + '%' }},
      }},
    }},
  }},
}});

// Per-week detail cards
const container = document.getElementById('weeks-list');
WEEKS.slice().reverse().forEach(w => {{
  const card = document.createElement('div');
  card.className = 'week-card';

  function pickTable(picks, isChallenger) {{
    if (!picks.length) return '<div style="padding:10px;color:var(--muted);font-size:11px;">No picks this week.</div>';
    const extraHeaders = isChallenger
      ? '<th>RSI</th><th>ROC5</th><th>Vol</th>'
      : '<th>Score</th>';
    const rows = picks.map(p => {{
      const pnlCls = p.pnl >= 0 ? 'pos' : 'neg';
      let daysCell;
      if (p.trunc5)         daysCell = '<td class="days-trunc">n/a</td>';
      else if (p.reached5)  daysCell = `<td class="days-reached">${{p.days5}}d</td>`;
      else                  daysCell = '<td class="days-not">>&{cap_days}d</td>';
      const extraCells = isChallenger
        ? `<td>${{p.rsi}}</td><td>${{p.roc5 >= 0 ? '+' : ''}}${{p.roc5}}%</td><td>${{p.vsurge}}×</td>`
        : `<td>${{p.score}}</td>`;
      return `<tr>
        <td>${{p.ticker}}</td>
        <td><span class="badge badge-${{p.type}}">${{p.type}}</span></td>
        <td>$${{p.entry}}</td>
        <td>$${{p.exit}}</td>
        <td class="${{pnlCls}}">${{p.pnl >= 0 ? '+' : ''}}${{p.pnl}}%</td>
        ${{daysCell}}
        ${{extraCells}}
      </tr>`;
    }}).join('');
    const extraH = isChallenger
      ? '<th>RSI</th><th>ROC5</th><th>Vol</th>'
      : '<th>Score</th>';
    return `<table><thead><tr>
      <th>Ticker</th><th>Type</th><th>Entry</th><th>Exit</th><th>P&L</th><th>→+5%</th>${{extraH}}
    </tr></thead><tbody>${{rows}}</tbody></table>`;
  }}

  const cBeat = w.champ_beat ? 'pos' : 'neg';
  const hBeat = w.chall_beat ? 'pos' : 'neg';
  const cIcon = w.champ_beat ? '▲' : '▼';
  const hIcon = w.chall_beat ? '▲' : '▼';

  card.innerHTML = `
    <div class="week-header" onclick="this.closest('.week-card').classList.toggle('open')">
      <span class="week-date">${{w.entry}} → ${{w.exit}}</span>
      <span class="week-returns">
        <span>Champ <span class="${{cBeat}}">${{w.champ_ret >= 0 ? '+' : ''}}${{w.champ_ret}}%</span> ${{cIcon}}</span>
        <span>Chall <span class="${{hBeat}}">${{w.chall_ret >= 0 ? '+' : ''}}${{w.chall_ret}}%</span> ${{hIcon}}</span>
        <span style="color:var(--muted)">SPY ${{w.spy_ret >= 0 ? '+' : ''}}${{w.spy_ret}}%</span>
      </span>
      <span class="chevron">▾</span>
    </div>
    <div class="week-body">
      <div class="picks-grid">
        <div class="picks-section">
          <div class="picks-label">Champion (${{w.champ_picks.length}} picks · ${{w.n_champ_cand}} candidates)</div>
          ${{pickTable(w.champ_picks, false)}}
        </div>
        <div class="picks-section">
          <div class="picks-label">Challenger (${{w.chall_picks.length}} picks · ${{w.n_chall_cand}} candidates)</div>
          ${{pickTable(w.chall_picks, true)}}
        </div>
      </div>
    </div>`;
  container.appendChild(card);
}});
</script>
</body>
</html>"""
