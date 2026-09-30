"""
report.py
Takes a list of 10 pick dicts and renders the Signal HTML report.
"""

from datetime import date, timedelta
import json
import urllib.request

_CHARTJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
_chartjs_cache: str | None = None


def _chartjs() -> str:
    global _chartjs_cache
    if _chartjs_cache is None:
        try:
            with urllib.request.urlopen(_CHARTJS_URL, timeout=15) as r:
                _chartjs_cache = r.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Could not fetch Chart.js for inline bundling: {e}")
    return _chartjs_cache


def next_report_date(today: date) -> date:
    """Return the date of the next Wednesday run."""
    days_until = (2 - today.weekday()) % 7  # 2 = Wednesday
    if days_until == 0:
        days_until = 7
    return today + timedelta(days=days_until)


def _color_de(de_val):
    """Return CSS class for debt/equity coloring."""
    if de_val is None or de_val == "N/A (ETF)":
        return "good"
    try:
        v = float(de_val)
        if v <= 0.3:
            return "good"
        if v <= 0.5:
            return "warn"
        return "bad"
    except Exception:
        return "good"


def render(picks: list[dict], report_date: date = None) -> str:
    """
    picks: list of dicts with keys:
      ticker, type (stock/etf), name, sector, price,
      returns (dict: 1M/1Y/3Y/5Y as strings),
      debt (str), desc, why,
      news (dict: prev/curr int),
      prices (list of floats, ~19 weekly closes over 6 months),
      cup (dict from cup_handle.detect)

    Returns full HTML string.
    """
    if report_date is None:
        report_date = date.today()

    next_date = next_report_date(report_date)
    report_date_str = report_date.strftime("%b %d, %Y")
    next_date_str = next_date.strftime("%b %d, %Y")

    # Determine issue number (weeks since anchor, divided by 2)
    anchor = date(2025, 5, 15)
    issue_num = max(1, ((report_date - anchor).days // 7) + 1)

    picks_json = json.dumps(picks)
    chartjs_src = _chartjs()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal — {report_date_str}</title>
<script>{chartjs_src}</script>
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
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--mono);
    font-size: 13px;
    line-height: 1.6;
    min-height: 100vh;
  }}
  header {{
    padding: 32px 20px 24px;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .header-top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .wordmark {{ font-size: 11px; letter-spacing: 0.2em; color: var(--muted); text-transform: uppercase; }}
  .report-date {{ font-size: 11px; color: var(--muted); text-align: right; }}
  .report-date span {{ display: block; color: var(--accent); }}
  h1 {{ font-family: var(--mono); font-size: 22px; font-weight: 300; letter-spacing: -0.02em; color: var(--text); margin-top: 12px; }}
  .subline {{ font-size: 11px; color: var(--muted); letter-spacing: 0.05em; }}
  .cards {{ padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 2px; overflow: hidden; transition: border-color 0.15s; }}
  .card.open {{ border-color: var(--border-active); }}
  .card-header {{ display: grid; grid-template-columns: 1fr auto; align-items: start; padding: 14px 16px; cursor: pointer; gap: 12px; user-select: none; }}
  .card-left {{ display: flex; flex-direction: column; gap: 3px; }}
  .ticker-row {{ display: flex; align-items: center; gap: 10px; }}
  .ticker {{ font-size: 15px; font-weight: 500; letter-spacing: 0.05em; color: var(--text); }}
  .badge {{ font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; padding: 2px 6px; border-radius: 1px; border: 1px solid; }}
  .badge-etf {{ color: #7eb8f7; border-color: rgba(126,184,247,0.3); }}
  .badge-stock {{ color: var(--muted); border-color: var(--border-active); }}
  .company-name {{ font-size: 11px; color: var(--muted); font-family: var(--sans); font-weight: 300; }}
  .sector-tag {{ font-size: 10px; color: #444; letter-spacing: 0.08em; text-transform: uppercase; }}
  .card-right {{ display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }}
  .price {{ font-size: 15px; font-weight: 400; }}
  .return-1m {{ font-size: 11px; color: var(--accent); }}
  .return-1m.neg {{ color: var(--red); }}
  .chevron {{ font-size: 10px; color: var(--muted); margin-top: 4px; transition: transform 0.2s; }}
  .card.open .chevron {{ transform: rotate(180deg); }}
  .card-body {{ display: none; border-top: 1px solid var(--border); }}
  .card.open .card-body {{ display: block; }}
  .section {{ padding: 14px 16px; border-bottom: 1px solid var(--border); }}
  .section:last-child {{ border-bottom: none; }}
  .section-label {{ font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }}
  .desc {{ font-family: var(--sans); font-size: 13px; font-weight: 300; color: #aaa; line-height: 1.7; }}
  .why-pick {{ font-size: 12px; color: var(--accent); font-family: var(--sans); line-height: 1.6; padding: 10px 12px; background: var(--accent-dim); border-left: 2px solid var(--accent); border-radius: 1px; }}
  .confidence-row {{ display: flex; align-items: center; gap: 8px; margin-top: 8px; }}
  .confidence-label {{ font-size: 10px; color: var(--muted); }}
  .confidence-bar {{ flex: 1; height: 2px; background: var(--border-active); border-radius: 2px; overflow: hidden; }}
  .confidence-fill {{ height: 100%; background: var(--accent); border-radius: 2px; }}
  .confidence-val {{ font-size: 10px; color: var(--accent); }}
  .metrics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .metric {{ display: flex; flex-direction: column; gap: 3px; }}
  .metric-label {{ font-size: 10px; color: var(--muted); letter-spacing: 0.06em; }}
  .metric-value {{ font-size: 14px; color: var(--text); }}
  .metric-value.good {{ color: var(--accent); }}
  .metric-value.warn {{ color: var(--orange); }}
  .metric-value.bad {{ color: var(--red); }}
  .news-bar {{ display: flex; flex-direction: column; gap: 8px; }}
  .news-row {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
  .news-week-label {{ font-size: 10px; color: var(--muted); min-width: 64px; }}
  .news-track {{ flex: 1; height: 3px; background: var(--border-active); border-radius: 2px; overflow: hidden; }}
  .news-fill {{ height: 100%; border-radius: 2px; background: var(--muted); }}
  .news-fill.surge {{ background: var(--accent); }}
  .news-count {{ font-size: 10px; color: var(--muted); min-width: 28px; text-align: right; }}
  .news-surge-label {{ font-size: 10px; color: var(--accent); letter-spacing: 0.08em; }}
  .chart-wrap {{ height: 160px; position: relative; }}
  .cup-label {{ position: absolute; font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); opacity: 0.7; top: 8px; right: 12px; }}
  footer {{ padding: 24px 20px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }}
  .footer-note {{ font-size: 10px; color: #333; max-width: 240px; line-height: 1.5; }}
  .next-report {{ font-size: 10px; color: var(--muted); text-align: right; }}
  .next-report span {{ display: block; color: var(--accent); margin-top: 2px; }}
</style>
</head>
<body>

<header>
  <div class="header-top">
    <div class="wordmark">Signal</div>
    <div class="report-date">
      Issue #{issue_num:02d}
      <span>{report_date_str}</span>
    </div>
  </div>
  <h1>Weekly Screen</h1>
  <div class="subline">10 picks — cup &amp; handle · low debt · news surge · cross-sector</div>
</header>

<div class="cards" id="cards"></div>

<footer>
  <div class="footer-note">Algorithmic screen. Not investment advice. Cup &amp; handle detection is pattern-based and approximate.</div>
  <div class="next-report">
    Next report
    <span>{next_date_str}</span>
  </div>
</footer>

<script>
const picks = {picks_json};

const container = document.getElementById('cards');
const maxNews = Math.max(...picks.map(p => p.news.curr));

picks.forEach((p, i) => {{
  const newsIndex = p.news_index ?? 0;
  const ret1m = p.returns['1M'] || '';
  const isNeg = ret1m.startsWith('-');
  const conf = p.cup ? p.cup.confidence : 0;
  const cupDetected = p.cup && p.cup.detected;

  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = `
    <div class="card-header">
      <div class="card-left">
        <div class="ticker-row">
          <span class="ticker">${{p.ticker}}</span>
          <span class="badge badge-${{p.type}}">${{p.type.toUpperCase()}}</span>
        </div>
        <div class="company-name">${{p.name}}</div>
        <div class="sector-tag">${{p.sector}}</div>
      </div>
      <div class="card-right">
        <div class="price">$${{p.price.toFixed(2)}}</div>
        <div class="return-1m ${{isNeg ? 'neg' : ''}}">${{ret1m}} <span style="font-size:9px;color:var(--muted)">1M</span></div>
        <div class="chevron">▼</div>
      </div>
    </div>
    <div class="card-body">
      <div class="section">
        <div class="section-label">About</div>
        <div class="desc">${{p.desc}}</div>
      </div>

      <div class="section">
        <div class="why-pick">${{p.why}}</div>
        ${{cupDetected ? `
        <div class="confidence-row">
          <div class="confidence-label">Pattern confidence</div>
          <div class="confidence-bar"><div class="confidence-fill" style="width:${{conf * 100}}%"></div></div>
          <div class="confidence-val">${{Math.round(conf * 100)}}%</div>
        </div>` : ''}}
      </div>

      <div class="section">
        <div class="section-label">Debt &amp; Returns</div>
        <div class="metrics-grid">
          <div class="metric">
            <div class="metric-label">Debt / Equity</div>
            <div class="metric-value ${{p.deRating}}">${{p.debt}}</div>
          </div>
          ${{Object.entries(p.returns).map(([k,v]) => `
          <div class="metric">
            <div class="metric-label">${{k}} Return</div>
            <div class="metric-value good">${{v}}</div>
          </div>`).join('')}}
        </div>
      </div>

      <div class="section">
        <div class="section-label">News Coverage — this week vs prior week</div>
        <div class="news-bar">
          <div class="news-row">
            <div class="news-week-label">Prior week</div>
            <div class="news-track"><div class="news-fill" style="width:${{(p.news.prev/maxNews)*100}}%"></div></div>
            <div class="news-count">${{p.news.prev}}</div>
          </div>
          <div class="news-row">
            <div class="news-week-label">This week</div>
            <div class="news-track"><div class="news-fill surge" style="width:${{(p.news.curr/maxNews)*100}}%"></div></div>
            <div class="news-count">${{p.news.curr}}</div>
          </div>
          <div class="news-surge-label">Coverage index: ${{newsIndex}} / 100 among screened</div>
        </div>
      </div>

      <div class="section" style="padding:0">
        <div class="chart-wrap">
          <div class="cup-label">Cup &amp; Handle ◦</div>
          <canvas id="chart-${{i}}"></canvas>
        </div>
      </div>
    </div>
  `;

  card.querySelector('.card-header').addEventListener('click', () => {{
    card.classList.toggle('open');
    if (card.classList.contains('open')) renderChart(i, p);
  }});

  container.appendChild(card);
}});

function renderChart(i, p) {{
  const canvas = document.getElementById(`chart-${{i}}`);
  if (canvas.dataset.rendered) return;
  canvas.dataset.rendered = '1';

  const prices = p.prices;
  const n = prices.length;
  const cup = p.cup;

  const pointColors = prices.map((_, idx) => {{
    if (!cup || !cup.detected) return 'rgba(200,245,66,0.4)';
    if (idx >= cup.handle_end) return 'rgba(200,245,66,0.9)';
    if (idx >= cup.cup_end) return 'rgba(200,245,66,0.7)';
    if (idx >= cup.cup_start) return 'rgba(200,245,66,0.4)';
    return 'rgba(100,100,100,0.3)';
  }});

  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const pad = (maxP - minP) * 0.15;

  new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: prices.map(() => ''),
      datasets: [{{
        data: prices,
        borderColor: 'rgba(200,245,66,0.6)',
        borderWidth: 1.5,
        pointRadius: 0,
        fill: {{ target: 'origin', above: 'rgba(200,245,66,0.04)' }},
        tension: 0.4
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{ label: ctx => `$${{ctx.parsed.y.toFixed(2)}}` }},
          backgroundColor: '#111',
          borderColor: '#222',
          borderWidth: 1,
          titleColor: '#555',
          bodyColor: '#e8e8e8',
          titleFont: {{ family: 'IBM Plex Mono', size: 10 }},
          bodyFont: {{ family: 'IBM Plex Mono', size: 12 }},
        }}
      }},
      scales: {{
        x: {{ display: false }},
        y: {{
          display: true,
          min: minP - pad,
          max: maxP + pad,
          grid: {{ color: 'rgba(255,255,255,0.03)' }},
          ticks: {{
            color: '#333',
            font: {{ family: 'IBM Plex Mono', size: 9 }},
            maxTicksLimit: 4,
            callback: v => `$${{v.toFixed(0)}}`
          }},
          border: {{ display: false }}
        }}
      }}
    }}
  }});
}}
</script>
</body>
</html>"""

    return html


def save(picks: list[dict], output_path: str, report_date: date = None, strategy=None):
    html = render(picks, report_date)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved to {output_path}")


def save_combined(champion_picks: list[dict], challenger_picks: list[dict],
                  output_path: str, report_date: date = None) -> None:
    html = render_combined(champion_picks, challenger_picks, report_date)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Combined report saved to {output_path}")


def render_combined(champion_picks: list[dict], challenger_picks: list[dict],
                    report_date: date = None) -> str:
    if report_date is None:
        report_date = date.today()

    next_date = next_report_date(report_date)
    report_date_str = report_date.strftime("%b %d, %Y")
    next_date_str   = next_date.strftime("%b %d, %Y")

    anchor    = date(2025, 5, 15)
    issue_num = max(1, ((report_date - anchor).days // 7) + 1)

    champ_json = json.dumps(champion_picks)
    chall_json = json.dumps(challenger_picks)
    chartjs    = _chartjs()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal — {report_date_str}</title>
<script>{chartjs}</script>
<style>
  :root {{
    --bg:#0a0a0a;--surface:#111111;--border:#1e1e1e;--border-active:#2e2e2e;
    --text:#e8e8e8;--muted:#555;--accent:#c8f542;--accent-dim:rgba(200,245,66,0.08);
    --red:#ff4d4d;--orange:#f5a623;--blue:#7eb8f7;
    --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{background:var(--bg);color:var(--text);font-family:var(--mono);font-size:13px;line-height:1.6;min-height:100vh;}}

  header{{padding:32px 20px 0;border-bottom:1px solid var(--border);}}
  .header-top{{display:flex;justify-content:space-between;align-items:flex-start;}}
  .wordmark{{font-size:11px;letter-spacing:0.2em;color:var(--muted);text-transform:uppercase;}}
  .report-date{{font-size:11px;color:var(--muted);text-align:right;}}
  .report-date span{{display:block;color:var(--accent);}}
  h1{{font-size:22px;font-weight:300;letter-spacing:-0.02em;margin-top:12px;}}
  .subline{{font-size:11px;color:var(--muted);letter-spacing:0.05em;margin-top:4px;}}

  .tab-bar{{display:flex;gap:0;margin-top:20px;}}
  .tab-btn{{
    font-family:var(--mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;
    padding:10px 20px;background:none;border:none;border-bottom:2px solid transparent;
    color:var(--muted);cursor:pointer;transition:color 0.15s,border-color 0.15s;
  }}
  .tab-btn:hover{{color:var(--text);}}
  .tab-btn.active{{color:var(--accent);border-bottom-color:var(--accent);}}
  .tab-btn.challenger-tab.active{{color:var(--orange);border-bottom-color:var(--orange);}}

  .tab-pane{{display:none;}} .tab-pane.visible{{display:block;}}

  .cards{{padding:12px 16px;display:flex;flex-direction:column;gap:8px;}}
  .card{{background:var(--surface);border:1px solid var(--border);border-radius:2px;overflow:hidden;transition:border-color 0.15s;}}
  .card.open{{border-color:var(--border-active);}}
  .card-header{{display:grid;grid-template-columns:1fr auto;align-items:start;padding:14px 16px;cursor:pointer;gap:12px;user-select:none;}}
  .card-left{{display:flex;flex-direction:column;gap:3px;}}
  .ticker-row{{display:flex;align-items:center;gap:10px;}}
  .ticker{{font-size:15px;font-weight:500;letter-spacing:0.05em;}}
  .badge{{font-size:9px;letter-spacing:0.12em;text-transform:uppercase;padding:2px 6px;border-radius:1px;border:1px solid;}}
  .badge-etf{{color:var(--blue);border-color:rgba(126,184,247,0.3);}}
  .badge-stock{{color:var(--muted);border-color:var(--border-active);}}
  .company-name{{font-size:11px;color:var(--muted);font-family:var(--sans);font-weight:300;}}
  .sector-tag{{font-size:10px;color:#444;letter-spacing:0.08em;text-transform:uppercase;}}
  .card-right{{display:flex;flex-direction:column;align-items:flex-end;gap:3px;}}
  .price{{font-size:15px;font-weight:400;}}
  .return-1m{{font-size:11px;color:var(--accent);}}
  .return-1m.neg{{color:var(--red);}}
  .chevron{{font-size:10px;color:var(--muted);margin-top:4px;transition:transform 0.2s;}}
  .card.open .chevron{{transform:rotate(180deg);}}
  .card-body{{display:none;border-top:1px solid var(--border);}}
  .card.open .card-body{{display:block;}}

  .section{{padding:14px 16px;border-bottom:1px solid var(--border);}}
  .section:last-child{{border-bottom:none;}}
  .section-label{{font-size:9px;letter-spacing:0.18em;text-transform:uppercase;color:var(--muted);margin-bottom:8px;}}
  .desc{{font-family:var(--sans);font-size:13px;font-weight:300;color:#aaa;line-height:1.7;}}
  .why-pick{{font-size:12px;font-family:var(--sans);line-height:1.6;padding:10px 12px;border-left:2px solid;border-radius:1px;}}
  .why-champion{{color:var(--accent);background:var(--accent-dim);border-color:var(--accent);}}
  .why-challenger{{color:var(--orange);background:rgba(245,166,35,0.07);border-color:var(--orange);}}

  /* Champion-specific */
  .confidence-row{{display:flex;align-items:center;gap:8px;margin-top:8px;}}
  .confidence-label{{font-size:10px;color:var(--muted);}}
  .confidence-bar{{flex:1;height:2px;background:var(--border-active);border-radius:2px;overflow:hidden;}}
  .confidence-fill{{height:100%;background:var(--accent);border-radius:2px;}}
  .confidence-val{{font-size:10px;color:var(--accent);}}
  .news-bar{{display:flex;flex-direction:column;gap:8px;}}
  .news-row{{display:flex;justify-content:space-between;align-items:center;gap:12px;}}
  .news-week-label{{font-size:10px;color:var(--muted);min-width:64px;}}
  .news-track{{flex:1;height:3px;background:var(--border-active);border-radius:2px;overflow:hidden;}}
  .news-fill{{height:100%;border-radius:2px;background:var(--muted);}}
  .news-fill.surge{{background:var(--accent);}}
  .news-count{{font-size:10px;color:var(--muted);min-width:28px;text-align:right;}}
  .news-surge-label{{font-size:10px;color:var(--accent);letter-spacing:0.08em;}}

  /* Challenger-specific momentum grid */
  .mom-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}}
  .mom-stat{{display:flex;flex-direction:column;gap:3px;}}
  .mom-label{{font-size:10px;color:var(--muted);letter-spacing:0.06em;}}
  .mom-value{{font-size:14px;}}
  .mom-value.pos{{color:var(--accent);}}
  .mom-value.neg{{color:var(--red);}}
  .mom-value.neu{{color:var(--text);}}
  .mom-value.ora{{color:var(--orange);}}
  .ema-badge{{font-size:10px;color:var(--orange);letter-spacing:0.06em;}}

  /* Shared metrics */
  .metrics-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
  .metric{{display:flex;flex-direction:column;gap:3px;}}
  .metric-label{{font-size:10px;color:var(--muted);letter-spacing:0.06em;}}
  .metric-value{{font-size:14px;}}
  .metric-value.good{{color:var(--accent);}}
  .metric-value.warn{{color:var(--orange);}}
  .metric-value.bad{{color:var(--red);}}

  .chart-wrap{{height:160px;position:relative;}}
  .chart-label{{position:absolute;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;opacity:0.7;top:8px;right:12px;}}
  .chart-label.champion{{color:var(--accent);}}
  .chart-label.challenger{{color:var(--orange);}}

  footer{{padding:24px 20px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;}}
  .footer-note{{font-size:10px;color:#333;max-width:280px;line-height:1.5;}}
  .next-report{{font-size:10px;color:var(--muted);text-align:right;}}
  .next-report span{{display:block;color:var(--accent);margin-top:2px;}}
</style>
</head>
<body>

<header>
  <div class="header-top">
    <div class="wordmark">Signal</div>
    <div class="report-date">Issue #{issue_num:02d}<span>{report_date_str}</span></div>
  </div>
  <h1>Weekly Screen</h1>
  <div class="subline">{len(champion_picks)} champion picks · {len(challenger_picks)} challenger picks</div>
  <div class="tab-bar">
    <button class="tab-btn active" data-tab="champion">V1 — Cup &amp; Handle</button>
    <button class="tab-btn challenger-tab" data-tab="challenger">V2 — Momentum</button>
  </div>
</header>

<div class="tab-pane visible" id="pane-champion">
  <div class="cards" id="cards-champion"></div>
</div>
<div class="tab-pane" id="pane-challenger">
  <div class="cards" id="cards-challenger"></div>
</div>

<footer>
  <div class="footer-note">Algorithmic screen. Not investment advice. V1: cup &amp; handle + news surge. V2: short-term momentum, 5-day hold horizon.</div>
  <div class="next-report">Next report<span>{next_date_str}</span></div>
</footer>

<script>
// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('visible'));
    btn.classList.add('active');
    document.getElementById('pane-' + btn.dataset.tab).classList.add('visible');
  }});
}});

// ── Shared card header ────────────────────────────────────────────────────────
function cardHeader(p) {{
  const ret1m = p.returns['1M'] || '';
  const isNeg = ret1m.startsWith('-');
  return `
    <div class="card-header">
      <div class="card-left">
        <div class="ticker-row">
          <span class="ticker">${{p.ticker}}</span>
          <span class="badge badge-${{p.type}}">${{p.type.toUpperCase()}}</span>
        </div>
        <div class="company-name">${{p.name}}</div>
        <div class="sector-tag">${{p.sector}}</div>
      </div>
      <div class="card-right">
        <div class="price">$${{p.price.toFixed(2)}}</div>
        <div class="return-1m ${{isNeg ? 'neg' : ''}}">${{ret1m}} <span style="font-size:9px;color:var(--muted)">1M</span></div>
        <div class="chevron">▼</div>
      </div>
    </div>`;
}}

// ── Champion cards ────────────────────────────────────────────────────────────
const champPicks = {champ_json};
const champContainer = document.getElementById('cards-champion');
const maxNews = Math.max(...champPicks.map(p => p.news ? p.news.curr : 0), 1);

champPicks.forEach((p, i) => {{
  const conf = p.cup ? p.cup.confidence : 0;
  const cupDetected = p.cup && p.cup.detected;
  const newsIndex = p.news_index ?? 0;

  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = cardHeader(p) + `
    <div class="card-body">
      <div class="section">
        <div class="section-label">About</div>
        <div class="desc">${{p.desc}}</div>
      </div>
      <div class="section">
        <div class="why-pick why-champion">${{p.why}}</div>
        ${{cupDetected ? `
        <div class="confidence-row">
          <div class="confidence-label">Pattern confidence</div>
          <div class="confidence-bar"><div class="confidence-fill" style="width:${{conf*100}}%"></div></div>
          <div class="confidence-val">${{Math.round(conf*100)}}%</div>
        </div>` : ''}}
      </div>
      <div class="section">
        <div class="section-label">Debt &amp; Returns</div>
        <div class="metrics-grid">
          <div class="metric"><div class="metric-label">Debt / Equity</div><div class="metric-value ${{p.deRating}}">${{p.debt}}</div></div>
          ${{Object.entries(p.returns).map(([k,v]) => `<div class="metric"><div class="metric-label">${{k}} Return</div><div class="metric-value good">${{v}}</div></div>`).join('')}}
        </div>
      </div>
      ${{p.news ? `
      <div class="section">
        <div class="section-label">News Coverage — this week vs prior week</div>
        <div class="news-bar">
          <div class="news-row">
            <div class="news-week-label">Prior week</div>
            <div class="news-track"><div class="news-fill" style="width:${{(p.news.prev/maxNews)*100}}%"></div></div>
            <div class="news-count">${{p.news.prev}}</div>
          </div>
          <div class="news-row">
            <div class="news-week-label">This week</div>
            <div class="news-track"><div class="news-fill surge" style="width:${{(p.news.curr/maxNews)*100}}%"></div></div>
            <div class="news-count">${{p.news.curr}}</div>
          </div>
          <div class="news-surge-label">Coverage index: ${{newsIndex}} / 100 among screened</div>
        </div>
      </div>` : ''}}
      <div class="section" style="padding:0">
        <div class="chart-wrap">
          <div class="chart-label champion">Cup &amp; Handle ◦</div>
          <canvas id="cchart-${{i}}"></canvas>
        </div>
      </div>
    </div>`;

  card.querySelector('.card-header').addEventListener('click', () => {{
    card.classList.toggle('open');
    if (card.classList.contains('open')) renderPriceChart(`cchart-${{i}}`, p, 'champion');
  }});
  champContainer.appendChild(card);
}});

// ── Challenger cards ──────────────────────────────────────────────────────────
const challPicks = {chall_json}.sort((a, b) =>
  ((b.momentum || {{}}).composite || 0) - ((a.momentum || {{}}).composite || 0)
);
const challContainer = document.getElementById('cards-challenger');

challPicks.forEach((p, i) => {{
  const mom = p.momentum || {{}};
  const rsi = mom.rsi ?? '—';
  const roc5pct = mom.roc5 != null ? ((mom.roc5 * 100).toFixed(1) + '%') : '—';
  const roc5cls = mom.roc5 >= 0 ? 'pos' : 'neg';
  const volSurge = mom.volume_surge != null ? (mom.volume_surge.toFixed(1) + '×') : '—';
  const emaLabel = mom.ema_label ?? '—';
  const r3m = mom.r3m != null ? ((mom.r3m*100).toFixed(1)+'%') : '—';
  const r6m = mom.r6m != null ? ((mom.r6m*100).toFixed(1)+'%') : '—';
  const r12m = mom.r12m != null ? ((mom.r12m*100).toFixed(1)+'%') : '—';
  const composite = mom.composite != null ? (mom.composite*100).toFixed(0) : '—';
  const emaFull = emaLabel.includes('full');

  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = cardHeader(p) + `
    <div class="card-body">
      <div class="section">
        <div class="section-label">About</div>
        <div class="desc">${{p.desc}}</div>
      </div>
      <div class="section">
        <div class="why-pick why-challenger">${{p.why}}</div>
      </div>
      <div class="section">
        <div class="section-label">Momentum Signals</div>
        <div class="mom-grid">
          <div class="mom-stat">
            <div class="mom-label">Composite</div>
            <div class="mom-value ora">${{composite}}/100</div>
          </div>
          <div class="mom-stat">
            <div class="mom-label">RSI (14)</div>
            <div class="mom-value neu">${{rsi}}</div>
          </div>
          <div class="mom-stat">
            <div class="mom-label">5-day ROC</div>
            <div class="mom-value ${{roc5cls}}">${{roc5pct}}</div>
          </div>
          <div class="mom-stat">
            <div class="mom-label">Volume surge</div>
            <div class="mom-value ${{mom.volume_surge >= 1.5 ? 'pos' : 'neu'}}">${{volSurge}}</div>
          </div>
          <div class="mom-stat">
            <div class="mom-label">3M / 6M / 12M</div>
            <div class="mom-value pos" style="font-size:12px">${{r3m}} / ${{r6m}} / ${{r12m}}</div>
          </div>
          <div class="mom-stat">
            <div class="mom-label">EMA alignment</div>
            <div class="ema-badge">${{emaFull ? '▲ full bull stack' : emaLabel}}</div>
          </div>
        </div>
      </div>
      <div class="section">
        <div class="section-label">Debt &amp; Returns</div>
        <div class="metrics-grid">
          <div class="metric"><div class="metric-label">Debt / Equity</div><div class="metric-value ${{p.deRating}}">${{p.debt}}</div></div>
          ${{Object.entries(p.returns).map(([k,v]) => `<div class="metric"><div class="metric-label">${{k}} Return</div><div class="metric-value good">${{v}}</div></div>`).join('')}}
        </div>
      </div>
      <div class="section" style="padding:0">
        <div class="chart-wrap">
          <div class="chart-label challenger">Momentum ◦</div>
          <canvas id="hchart-${{i}}"></canvas>
        </div>
      </div>
    </div>`;

  card.querySelector('.card-header').addEventListener('click', () => {{
    card.classList.toggle('open');
    if (card.classList.contains('open')) renderPriceChart(`hchart-${{i}}`, p, 'challenger');
  }});
  challContainer.appendChild(card);
}});

// ── Shared price chart renderer ───────────────────────────────────────────────
function renderPriceChart(canvasId, p, mode) {{
  const canvas = document.getElementById(canvasId);
  if (!canvas || canvas.dataset.rendered) return;
  canvas.dataset.rendered = '1';

  const prices = p.prices;
  const cup    = p.cup;
  const accentColor = mode === 'challenger' ? 'rgba(245,166,35,' : 'rgba(200,245,66,';
  const borderColor = accentColor + '0.6)';
  const fillColor   = accentColor + '0.04)';

  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const pad  = (maxP - minP) * 0.15;

  new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: prices.map(() => ''),
      datasets: [{{
        data: prices,
        borderColor,
        borderWidth: 1.5,
        pointRadius: 0,
        fill: {{ target: 'origin', above: fillColor }},
        tension: 0.4,
      }}],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{ label: ctx => `$${{ctx.parsed.y.toFixed(2)}}` }},
          backgroundColor: '#111', borderColor: '#222', borderWidth: 1,
          titleColor: '#555', bodyColor: '#e8e8e8',
        }},
      }},
      scales: {{
        x: {{ display: false }},
        y: {{
          display: true,
          min: minP - pad, max: maxP + pad,
          grid: {{ color: 'rgba(255,255,255,0.03)' }},
          ticks: {{
            color: '#333', font: {{ size: 9 }},
            maxTicksLimit: 4, callback: v => `$${{v.toFixed(0)}}`,
          }},
          border: {{ display: false }},
        }},
      }},
    }},
  }});
}}
</script>
</body>
</html>"""
