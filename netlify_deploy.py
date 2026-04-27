"""
netlify_deploy.py
Generates the full interactive HTML tracker and deploys it to
the same Netlify site every time — keeping the URL permanent.

Flow:
  1. build_html(recs_data)  → returns HTML string
  2. deploy(html_str)       → zips, POSTs to Netlify API, returns site URL
"""

import os, io, json, zipfile, logging
import requests as req

log = logging.getLogger(__name__)

NETLIFY_TOKEN   = os.environ["NETLIFY_TOKEN"]     # Personal Access Token
NETLIFY_SITE_ID = os.environ["NETLIFY_SITE_ID"]   # e.g. abc123.netlify.app or site UUID

NETLIFY_DEPLOY_URL = f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys"

IMPACT_LABELS = {"pos": "🟢", "neu": "⚪", "neg": "🔴"}

# ── HTML builder ──────────────────────────────────────────────────────────────
def build_html(recs_data: list, news_events: list, generated_at: str) -> str:
    recs_json  = json.dumps(recs_data,  default=str)
    news_json  = json.dumps(news_events, default=str)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio Tracker — {generated_at}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8f7f4;color:#2c2c2a;padding:16px}}
  .header{{max-width:900px;margin:0 auto 20px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
  h1{{font-size:18px;font-weight:600}}
  .updated{{font-size:12px;color:#888}}
  .cards{{max-width:900px;margin:0 auto 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
  .card{{background:#fff;border:1px solid #e8e6e0;border-radius:10px;padding:12px 14px;cursor:pointer;transition:border-color .15s}}
  .card:hover,.card.active{{border-color:#378ADD}}
  .card.active{{background:#EEF5FD}}
  .sym{{font-size:14px;font-weight:600}}
  .card.active .sym{{color:#378ADD}}
  .meta{{font-size:11px;color:#888;margin-top:2px}}
  .price{{font-size:11px;color:#555;margin-top:3px}}
  .target{{font-size:11px;color:#1D9E75;font-weight:600;margin-top:2px}}
  .tag{{display:inline-block;font-size:10px;padding:2px 6px;border-radius:4px;background:#f0eee8;color:#666;margin-top:4px}}
  .perf{{max-width:900px;margin:0 auto 12px;display:flex;gap:8px;flex-wrap:wrap}}
  .badge{{font-size:12px;padding:4px 10px;border-radius:6px;border:1px solid #e8e6e0}}
  .badge.pos{{background:#eaf3de;color:#3b6d11;border-color:#c5dfa5}}
  .badge.neg{{background:#fcebeb;color:#a32d2d;border-color:#f0b8b8}}
  .badge.neu{{background:#f0eee8;color:#666}}
  .chart-box{{max-width:900px;margin:0 auto 16px;background:#fff;border:1px solid #e8e6e0;border-radius:10px;padding:16px}}
  .chart-title{{font-size:14px;font-weight:600;margin-bottom:4px}}
  .legend{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px}}
  .li{{display:flex;align-items:center;gap:5px;font-size:11px;color:#666}}
  .lline{{width:18px;height:2px;border-radius:1px}}
  .ldot{{width:8px;height:8px;border-radius:50%}}
  .period-row{{display:flex;gap:6px;margin-bottom:12px}}
  .pbtn{{font-size:11px;padding:3px 10px;border-radius:5px;border:1px solid #e8e6e0;background:transparent;cursor:pointer}}
  .pbtn.active{{background:#f0eee8;font-weight:600}}
  canvas{{width:100%!important}}
  .news-box{{max-width:900px;margin:0 auto 16px;background:#fff;border:1px solid #e8e6e0;border-radius:10px;padding:14px 16px}}
  .news-box h3{{font-size:13px;font-weight:600;margin-bottom:10px}}
  .nitem{{display:flex;gap:10px;align-items:flex-start;padding:8px;border-radius:6px;background:#f8f7f4;margin-bottom:6px}}
  .ndate{{font-size:10px;font-weight:600;padding:2px 6px;border-radius:3px;white-space:nowrap;flex-shrink:0;margin-top:1px}}
  .ntext{{font-size:12px;line-height:1.45}}
  .nsym{{font-size:10px;color:#888;margin-top:2px}}
  .footer{{max-width:900px;margin:20px auto 0;font-size:11px;color:#aaa;text-align:center}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>📈 Portfolio Tracker</h1>
    <div style="font-size:12px;color:#888;margin-top:2px">Advisor: +91 877 990 0557</div>
  </div>
  <div class="updated">Updated: {generated_at}</div>
</div>

<div class="cards" id="cards"></div>
<div class="perf" id="perf"></div>

<div class="chart-box">
  <div class="chart-title" id="ctitle">Select a stock</div>
  <div class="legend">
    <div class="li"><div class="lline" style="background:#378ADD"></div>Stock (rebased)</div>
    <div class="li"><div class="lline" style="background:#1D9E75;border-top:2px dashed #1D9E75;height:0"></div>Nifty 50</div>
    <div class="li"><div class="lline" style="background:#D85A30;border-top:2px dashed #D85A30;height:0"></div>Sensex</div>
    <div class="li"><div class="ldot" style="background:#D4537E"></div>News</div>
    <div class="li"><div style="width:2px;height:14px;background:#F0997B;border-radius:1px"></div>Buy date</div>
  </div>
  <div class="period-row" id="pbtns">
    <button class="pbtn active" data-days="14">14D</button>
    <button class="pbtn" data-days="30">30D</button>
    <button class="pbtn" data-days="60">60D</button>
    <button class="pbtn" data-days="9999">All</button>
  </div>
  <div style="position:relative;height:300px">
    <canvas id="chart"></canvas>
  </div>
  <div id="fetchnote" style="font-size:11px;color:#aaa;margin-top:6px;font-style:italic"></div>
</div>

<div class="news-box">
  <h3>News events</h3>
  <div id="newslist"></div>
</div>

<div class="footer">Data sourced via Yahoo Finance · Simulated prices shown (live data fetched by bot at {generated_at})</div>

<script>
const RECS = {recs_json};
const NEWS = {news_json};

let sel = 0, period = 14, chart = null;
const sign = v => v >= 0 ? '+' : '';
const cls  = v => Math.abs(v) < 0.5 ? 'neu' : v > 0 ? 'pos' : 'neg';

// ── Rebase utility ─────────────────────────────────────────────────────────
function rebase(prices) {{
  if (!prices || !prices.length) return [];
  const b = prices[0];
  return prices.map(p => +((p / b * 100).toFixed(2)));
}}

function pct(rb) {{
  return rb && rb.length ? +(rb[rb.length-1] - 100).toFixed(2) : 0;
}}

// ── Render cards ──────────────────────────────────────────────────────────
function renderCards() {{
  document.getElementById('cards').innerHTML = RECS.map((r,i) => `
    <div class="card ${{i===sel?'active':''}}" onclick="pick(${{i}})">
      <div class="sym">${{r.label}}</div>
      <div class="meta">Rec: ${{r.buy_date}}</div>
      <div class="price">Buy ₹${{r.buy_low}}–${{r.buy_high}}</div>
      ${{r.target ? `<div class="target">Target ₹${{r.target}}</div>` : ''}}
      <div class="tag">${{r.type}}</div>
    </div>`).join('');
}}

// ── Render performance badges ─────────────────────────────────────────────
function renderPerf(rb_s, rb_n, rb_x, rec) {{
  const sp = pct(rb_s), np = pct(rb_n), xp = pct(rb_x), al = +(sp-np).toFixed(2);
  document.getElementById('perf').innerHTML = `
    <div class="badge ${{cls(sp)}}">${{rec.label}}: ${{sign(sp)}}${{sp}}%</div>
    <div class="badge ${{cls(np)}}">Nifty 50: ${{sign(np)}}${{np}}%</div>
    <div class="badge ${{cls(xp)}}">Sensex: ${{sign(xp)}}${{xp}}%</div>
    <div class="badge ${{cls(al)}}">Alpha vs Nifty: ${{sign(al)}}${{al}}%</div>`;
}}

// ── Build chart ───────────────────────────────────────────────────────────
function buildChart(rec) {{
  if (chart) {{ chart.destroy(); chart = null; }}
  const ctx = document.getElementById('chart');
  const buyDt = new Date(rec.buy_date);
  const today = new Date();
  const maxDays = Math.min(period, Math.round((today - buyDt) / 86400000));

  // Build date labels from buy_date
  const labels = [];
  for (let i = 0; i <= maxDays; i++) {{
    const d = new Date(buyDt);
    d.setDate(d.getDate() + i);
    labels.push(d.toLocaleDateString('en-IN', {{day:'2-digit', month:'short'}}));
  }}

  // Use live prices from recs_data if present, else simulate
  const stockPrices = rec.stock_closes && rec.stock_closes.length
    ? rec.stock_closes.slice(0, maxDays+1)
    : simulate(rec.buy_low, maxDays, 0.14, 0.22, rec.label.charCodeAt(0));

  const niftyPrices = rec.nifty_closes && rec.nifty_closes.length
    ? rec.nifty_closes.slice(0, maxDays+1)
    : simulate(100, maxDays, 0.10, 0.13, 42);

  const sensexPrices = rec.sensex_closes && rec.sensex_closes.length
    ? rec.sensex_closes.slice(0, maxDays+1)
    : simulate(100, maxDays, 0.09, 0.12, 99);

  const rb_s = rebase(stockPrices);
  const rb_n = rebase(niftyPrices);
  const rb_x = rebase(sensexPrices);

  renderPerf(rb_s, rb_n, rb_x, rec);

  const buyDays = (today - buyDt) / 86400000 | 0;
  document.getElementById('ctitle').textContent =
    `${{rec.name}} (${{rec.label}}) · ${{buyDays}}d since recommendation`;
  document.getElementById('fetchnote').textContent =
    rec.stock_closes && rec.stock_closes.length
      ? `Live prices fetched at ${{'{generated_at}'}}`
      : `Simulated prices — live data loaded by bot at ${{'{generated_at}'}}`;

  // News annotations
  const newsForStock = NEWS.filter(n => n.symbol === 'ALL' || n.symbol === rec.label);
  const newsPlugin = {{
    id: 'newsMarkers',
    afterDraw(ch) {{
      const meta = ch.getDatasetMeta(0);
      if (!meta || !meta.data) return;
      newsForStock.forEach(n => {{
        const nDate = new Date(n.date);
        const idx = Math.round((nDate - buyDt) / 86400000);
        if (idx < 0 || idx >= meta.data.length) return;
        const pt = meta.data[idx];
        const c = ch.ctx;
        c.save();
        c.beginPath();
        c.arc(pt.x, pt.y, 5, 0, Math.PI*2);
        c.fillStyle = n.impact==='pos'?'#3B6D11':n.impact==='neg'?'#A32D2D':'#888';
        c.fill();
        c.strokeStyle = '#fff'; c.lineWidth = 1.5; c.stroke();
        c.restore();
      }});
    }}
  }};

  const buyLinePlugin = {{
    id: 'buyLine',
    afterDraw(ch) {{
      const {{ ctx, chartArea: {{top,bottom}}, scales: {{x}} }} = ch;
      const xp = x.getPixelForValue(0);
      ctx.save();
      ctx.setLineDash([4,3]);
      ctx.strokeStyle = '#F0997B'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(xp, top); ctx.lineTo(xp, bottom); ctx.stroke();
      ctx.setLineDash([]);
      const lbl = `Buy ₹${{rec.buy_low}}`;
      ctx.font = 'bold 10px sans-serif';
      const tw = ctx.measureText(lbl).width;
      ctx.fillStyle = '#F0997B';
      ctx.beginPath();
      ctx.roundRect(xp+4, top+6, tw+10, 18, 3);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.textBaseline = 'middle';
      ctx.fillText(lbl, xp+9, top+15);
      ctx.restore();
    }}
  }};

  chart = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels,
      datasets: [
        {{ label: rec.label,   data: rb_s, borderColor:'#378ADD', borderWidth:2,   pointRadius:0, tension:0.3, fill:false }},
        {{ label: 'Nifty 50',  data: rb_n, borderColor:'#1D9E75', borderWidth:1.3, pointRadius:0, tension:0.3, fill:false, borderDash:[5,3] }},
        {{ label: 'Sensex',    data: rb_x, borderColor:'#D85A30', borderWidth:1.3, pointRadius:0, tension:0.3, fill:false, borderDash:[3,3] }},
      ]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction:{{ mode:'index', intersect:false }},
      plugins:{{ legend:{{ display:false }}, tooltip:{{ callbacks:{{ label: c => `${{c.dataset.label}}: ${{(+c.raw).toFixed(1)}}%` }} }} }},
      scales:{{
        x:{{ ticks:{{ font:{{size:10}}, maxTicksLimit:10, color:'#888' }}, grid:{{ color:'rgba(0,0,0,0.04)' }} }},
        y:{{ ticks:{{ font:{{size:10}}, color:'#888', callback:v => v.toFixed(0)+'%' }}, grid:{{ color:'rgba(0,0,0,0.04)' }},
             title:{{ display:true, text:'Rebased (100 = buy date)', font:{{size:10}}, color:'#aaa' }} }}
      }}
    }},
    plugins: [buyLinePlugin, newsPlugin]
  }});
}}

// ── Simulate prices (fallback when live data absent) ──────────────────────
function simulate(start, days, drift, vol, seed) {{
  let s = seed * 9301 + 49297;
  const rand = () => {{ s = (s * 9301 + 49297) % 233280; return s/233280; }};
  const prices = [start];
  for (let i = 0; i < days; i++) {{
    const prev = prices[prices.length-1];
    prices.push(Math.max(prev*0.8, prev*(1 + drift/252 + vol*(rand()-0.48)*Math.sqrt(1/252))));
  }}
  return prices;
}}

// ── News list ─────────────────────────────────────────────────────────────
function renderNews() {{
  const rec = RECS[sel];
  const relevant = NEWS.filter(n => n.symbol==='ALL' || n.symbol===rec.label)
    .sort((a,b)=>a.date.localeCompare(b.date));
  const bgmap = {{pos:['#eaf3de','#3b6d11'], neg:['#fcebeb','#a32d2d'], neu:['#f0eee8','#555']}};
  document.getElementById('newslist').innerHTML = relevant.map(n => {{
    const [bg,fg] = bgmap[n.impact]||bgmap.neu;
    return `<div class="nitem">
      <div class="ndate" style="background:${{bg}};color:${{fg}}">${{n.date}}</div>
      <div><div class="ntext">${{n.text}}</div>
           <div class="nsym">${{n.symbol==='ALL'?'All stocks':n.symbol}}</div></div>
    </div>`;
  }}).join('') || '<div style="font-size:12px;color:#aaa">No news for this stock.</div>';
}}

// ── Interaction ───────────────────────────────────────────────────────────
function pick(i) {{ sel=i; renderCards(); buildChart(RECS[i]); renderNews(); }}

document.getElementById('pbtns').addEventListener('click', e => {{
  if (!e.target.dataset.days) return;
  period = +e.target.dataset.days;
  document.querySelectorAll('.pbtn').forEach(b=>b.classList.remove('active'));
  e.target.classList.add('active');
  buildChart(RECS[sel]);
}});

// ── Init ──────────────────────────────────────────────────────────────────
renderCards();
pick(0);
</script>
</body>
</html>"""


# ── Netlify deploy ────────────────────────────────────────────────────────────
def deploy(html: str) -> str:
    """
    Zips the HTML as index.html and POSTs to Netlify deploy API.
    Returns the live URL of the site.
    Raises on failure so the bot can log and continue without crashing.
    """
    # Build in-memory zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html)
    buf.seek(0)

    headers = {
        "Authorization": f"Bearer {NETLIFY_TOKEN}",
        "Content-Type":  "application/zip",
    }

    log.info(f"Deploying to Netlify site {NETLIFY_SITE_ID}…")
    resp = req.post(
        NETLIFY_DEPLOY_URL,
        headers=headers,
        data=buf.read(),
        timeout=60,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Netlify deploy failed {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    # 'ssl_url' is the https version, 'url' is http
    site_url = data.get("ssl_url") or data.get("url") or f"https://{NETLIFY_SITE_ID}"
    log.info(f"Deployed → {site_url}")
    return site_url
