"""
netlify_deploy.py  v2
Fixes:
  1. HTML built via string concat — no f-string brace escaping corruption
  2. Actual price (Rs.) shown in card tiles alongside % change
  3. Tooltip shows BOTH rebased % AND raw price for each series
"""

import io, json, zipfile, logging, os
import requests as req

log = logging.getLogger(__name__)


def build_html(recs_data: list, news_events: list, generated_at: str) -> str:
    recs_json = json.dumps(recs_data,  default=str)
    news_json = json.dumps(news_events, default=str)
    ts_json   = json.dumps(generated_at)   # safely quoted JS string

    css = """* {box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8f7f4;color:#2c2c2a;padding:16px}
.header{max-width:900px;margin:0 auto 20px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}
h1{font-size:18px;font-weight:500}
.sub{font-size:12px;color:#888;margin-top:2px}
.updated{font-size:12px;color:#888}
.cards{max-width:900px;margin:0 auto 16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:10px}
.card{background:#fff;border:1px solid #e8e6e0;border-radius:10px;padding:12px 14px;cursor:pointer;transition:border-color .15s}
.card:hover,.card.active{border-color:#378ADD}
.card.active{background:#EEF5FD}
.sym{font-size:14px;font-weight:600}
.card.active .sym{color:#378ADD}
.cm{font-size:11px;color:#888;margin-top:2px}
.cp{font-size:11px;color:#555;margin-top:3px}
.ct{font-size:11px;color:#1D9E75;font-weight:600;margin-top:2px}
.cv{font-size:14px;font-weight:600;margin-top:6px}
.cpct{font-size:11px;margin-top:1px}
.ctag{display:inline-block;font-size:10px;padding:2px 6px;border-radius:4px;background:#f0eee8;color:#666;margin-top:4px}
.perf{max-width:900px;margin:0 auto 12px;display:flex;gap:8px;flex-wrap:wrap}
.badge{font-size:12px;padding:4px 10px;border-radius:6px;border:1px solid #e8e6e0}
.pos{background:#eaf3de;color:#3b6d11;border-color:#c5dfa5}
.neg{background:#fcebeb;color:#a32d2d;border-color:#f0b8b8}
.neu{background:#f0eee8;color:#666}
.cbox{max-width:900px;margin:0 auto 16px;background:#fff;border:1px solid #e8e6e0;border-radius:10px;padding:16px}
.ctitle{font-size:14px;font-weight:500;margin-bottom:4px}
.leg{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:10px}
.li{display:flex;align-items:center;gap:5px;font-size:11px;color:#666}
.ll{width:18px;height:2px;border-radius:1px}
.ld{width:8px;height:8px;border-radius:50%}
.prow{display:flex;gap:6px;margin-bottom:10px}
.pbtn{font-size:11px;padding:3px 10px;border-radius:5px;border:1px solid #e8e6e0;background:transparent;cursor:pointer}
.pbtn.active{background:#f0eee8;font-weight:600}
.cwrap{position:relative;height:300px}
.note{font-size:11px;color:#aaa;margin-top:6px;font-style:italic}
.nbox{max-width:900px;margin:0 auto 16px;background:#fff;border:1px solid #e8e6e0;border-radius:10px;padding:14px 16px}
.nbox h3{font-size:13px;font-weight:500;margin-bottom:10px}
.ni{display:flex;gap:10px;align-items:flex-start;padding:8px;border-radius:6px;background:#f8f7f4;margin-bottom:6px}
.nd{font-size:10px;font-weight:600;padding:2px 6px;border-radius:3px;white-space:nowrap;flex-shrink:0;margin-top:1px}
.nt{font-size:12px;line-height:1.45;color:#2c2c2a}
.ns{font-size:10px;color:#888;margin-top:2px}
.footer{max-width:900px;margin:20px auto 0;font-size:11px;color:#aaa;text-align:center}"""

    # JS written as plain string — __RECS__ __NEWS__ __TS__ replaced below
    js = r"""
const RECS = __RECS__;
const NEWS = __NEWS__;
const TS   = __TS__;

let sel=0, period=14, chart=null;
const sign = v => v>=0?'+':'';
const cls  = v => Math.abs(v)<0.5?'neu':v>0?'pos':'neg';
const fmtR = v => '\u20b9'+Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
const fmtP = v => (v>=0?'+':'')+v.toFixed(2)+'%';

function rebase(arr){
  if(!arr||!arr.length)return[];
  const b=arr[0]; return arr.map(p=>+((p/b*100).toFixed(2)));
}
function pct(rb){return rb&&rb.length?+(rb[rb.length-1]-100).toFixed(2):0;}
function lastV(arr){return arr&&arr.length?arr[arr.length-1]:null;}

function renderCards(){
  document.getElementById('cards').innerHTML=RECS.map((r,i)=>{
    const rb=r.stock_rb||[]; const raw=r.stock_closes||[];
    const sp=pct(rb); const curr=lastV(raw);
    const days=Math.round((Date.now()-new Date(r.buy_date))/86400000);
    const col=sp>=0?'#1D9E75':'#A32D2D';
    return `<div class="card${i===sel?' active':''}" onclick="pick(${i})">
      <div class="sym">${r.label}</div>
      <div class="cm">Rec: ${r.buy_date} &middot; ${days}d held</div>
      <div class="cp">Buy \u20b9${r.buy_low}&ndash;${r.buy_high}</div>
      ${r.target?`<div class="ct">Target \u20b9${r.target}</div>`:''}
      ${curr?`<div class="cv" style="color:${col}">${fmtR(curr)}</div>`:''}
      ${rb.length?`<div class="cpct" style="color:${col}">${fmtP(sp)} since rec</div>`:''}
      <div class="ctag">${r.type}</div>
    </div>`;
  }).join('');
}

function renderPerf(rb_s,rb_n,rb_x,raw_s,rec){
  const sp=pct(rb_s),np=pct(rb_n),xp=pct(rb_x),al=+(sp-np).toFixed(2);
  const curr=lastV(raw_s);
  document.getElementById('perf').innerHTML=`
    <div class="badge ${cls(sp)}">${rec.label}: ${fmtP(sp)}${curr?' ('+fmtR(curr)+')':''}</div>
    <div class="badge ${cls(np)}">Nifty 50: ${fmtP(np)}</div>
    <div class="badge ${cls(xp)}">Sensex: ${fmtP(xp)}</div>
    <div class="badge ${cls(al)}">Alpha vs Nifty: ${sign(al)}${al}%</div>`;
}

function buildChart(rec){
  if(chart){chart.destroy();chart=null;}
  const ctx=document.getElementById('chart');
  const buyDt=new Date(rec.buy_date);
  const maxD=Math.min(period,Math.round((Date.now()-buyDt)/86400000));
  const labels=[];
  for(let i=0;i<=maxD;i++){const d=new Date(buyDt);d.setDate(d.getDate()+i);
    labels.push(d.toLocaleDateString('en-IN',{day:'2-digit',month:'short'}));}

  const rawS=(rec.stock_closes||[]).slice(0,maxD+1);
  const rawN=(rec.nifty_closes||[]).slice(0,maxD+1);
  const rawX=(rec.sensex_closes||[]).slice(0,maxD+1);
  const rb_s=rec.stock_rb ?rec.stock_rb.slice(0,maxD+1) :rebase(rawS);
  const rb_n=rec.nifty_rb ?rec.nifty_rb.slice(0,maxD+1) :rebase(rawN);
  const rb_x=rec.sensex_rb?rec.sensex_rb.slice(0,maxD+1):rebase(rawX);

  renderPerf(rb_s,rb_n,rb_x,rawS,rec);
  const days=Math.round((Date.now()-buyDt)/86400000);
  document.getElementById('ctitle').textContent=`${rec.name} (${rec.label}) \u00b7 ${days}d since recommendation`;
  document.getElementById('note').textContent=rawS.length?`Live prices \u00b7 Updated ${TS}`:`Simulated prices \u00b7 ${TS}`;

  const newsFor=NEWS.filter(n=>n.symbol==='ALL'||n.symbol===rec.label);

  chart=new Chart(ctx,{
    type:'line',
    data:{labels,datasets:[
      {label:rec.label, data:rb_s,borderColor:'#378ADD',borderWidth:2,  pointRadius:0,tension:0.3,fill:false},
      {label:'Nifty 50',data:rb_n,borderColor:'#1D9E75',borderWidth:1.3,pointRadius:0,tension:0.3,fill:false,borderDash:[5,3]},
      {label:'Sensex',  data:rb_x,borderColor:'#D85A30',borderWidth:1.3,pointRadius:0,tension:0.3,fill:false,borderDash:[3,3]},
    ]},
    options:{
      responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{callbacks:{label:ctx=>{
          const ds=ctx.dataset.label, rb=+ctx.raw, idx=ctx.dataIndex;
          let raw=null;
          if(ds===rec.label) raw=rawS[idx]??null;
          if(ds==='Nifty 50') raw=rawN[idx]??null;
          if(ds==='Sensex')   raw=rawX[idx]??null;
          const pStr=(rb-100).toFixed(2), sg=rb>=100?'+':'';
          const rStr=raw!=null?'  '+fmtR(raw):'';
          return `${ds}: ${sg}${pStr}%${rStr}`;
        }}}
      },
      scales:{
        x:{ticks:{font:{size:10},maxTicksLimit:10,color:'#888'},grid:{color:'rgba(0,0,0,0.04)'}},
        y:{ticks:{font:{size:10},color:'#888',callback:v=>v.toFixed(0)+'%'},
           grid:{color:'rgba(0,0,0,0.04)'},
           title:{display:true,text:'Rebased (100 = buy date)',font:{size:10},color:'#aaa'}}
      }
    },
    plugins:[
      {id:'buyLine',afterDraw(ch){
        const{ctx:c,chartArea:{top,bottom},scales:{x}}=ch;
        const xp=x.getPixelForValue(0);
        c.save();c.setLineDash([4,3]);
        c.strokeStyle='#F0997B';c.lineWidth=2;
        c.beginPath();c.moveTo(xp,top);c.lineTo(xp,bottom);c.stroke();
        c.setLineDash([]);
        const lbl=`Buy \u20b9${rec.buy_low}`;
        c.font='bold 10px sans-serif';
        const tw=c.measureText(lbl).width;
        c.fillStyle='#F0997B';c.beginPath();
        c.roundRect(xp+4,top+6,tw+10,18,3);c.fill();
        c.fillStyle='#fff';c.textBaseline='middle';
        c.fillText(lbl,xp+9,top+15);c.restore();
      }},
      {id:'newsMarkers',afterDraw(ch){
        const meta=ch.getDatasetMeta(0);
        if(!meta||!meta.data)return;
        newsFor.forEach(n=>{
          const idx=Math.round((new Date(n.date)-buyDt)/86400000);
          if(idx<0||idx>=meta.data.length)return;
          const pt=meta.data[idx];const c=ch.ctx;
          c.save();c.beginPath();c.arc(pt.x,pt.y,5,0,Math.PI*2);
          c.fillStyle=n.impact==='pos'?'#3B6D11':n.impact==='neg'?'#A32D2D':'#888';
          c.fill();c.strokeStyle='#fff';c.lineWidth=1.5;c.stroke();c.restore();
        });
      }}
    ]
  });
}

function renderNews(){
  const rec=RECS[sel];
  const rel=NEWS.filter(n=>n.symbol==='ALL'||n.symbol===rec.label)
                .sort((a,b)=>a.date.localeCompare(b.date));
  const bm={pos:['#eaf3de','#3b6d11'],neg:['#fcebeb','#a32d2d'],neu:['#f0eee8','#555']};
  document.getElementById('newslist').innerHTML=rel.map(n=>{
    const[bg,fg]=bm[n.impact]||bm.neu;
    return `<div class="ni">
      <div class="nd" style="background:${bg};color:${fg}">${n.date}</div>
      <div><div class="nt">${n.text}</div>
           <div class="ns">${n.symbol==='ALL'?'All stocks':n.symbol}</div></div>
    </div>`;
  }).join('')||'<div style="font-size:12px;color:#aaa">No news for this stock.</div>';
}

function pick(i){sel=i;renderCards();buildChart(RECS[i]);renderNews();}
document.getElementById('pbtns').addEventListener('click',e=>{
  if(!e.target.dataset.days)return;
  period=+e.target.dataset.days;
  document.querySelectorAll('.pbtn').forEach(b=>b.classList.remove('active'));
  e.target.classList.add('active');buildChart(RECS[sel]);
});
renderCards();pick(0);
"""

    js = js.replace("__RECS__", recs_json)
    js = js.replace("__NEWS__", news_json)
    js = js.replace("__TS__",   ts_json)

    return (
        "<!DOCTYPE html><html lang='en'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
        f"<title>Portfolio Tracker \u2014 {generated_at}</title>"
        "<script src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js'></script>"
        "<style>" + css + "</style></head><body>"
        "<div class='header'>"
        f"<div><h1>Portfolio Tracker</h1><div class='sub'>Advisor: +91 877 990 0557</div></div>"
        f"<div class='updated'>Updated: {generated_at}</div>"
        "</div>"
        "<div class='cards' id='cards'></div>"
        "<div class='perf'  id='perf'></div>"
        "<div class='cbox'>"
        "<div class='ctitle' id='ctitle'>Select a stock</div>"
        "<div class='leg'>"
        "<div class='li'><div class='ll' style='background:#378ADD'></div>Stock (rebased)</div>"
        "<div class='li'><div class='ll' style='background:#1D9E75;border-top:2px dashed #1D9E75;height:0'></div>Nifty 50</div>"
        "<div class='li'><div class='ll' style='background:#D85A30;border-top:2px dashed #D85A30;height:0'></div>Sensex</div>"
        "<div class='li'><div class='ld' style='background:#D4537E'></div>News</div>"
        "<div class='li'><div style='width:2px;height:14px;background:#F0997B;border-radius:1px'></div>Buy date</div>"
        "</div>"
        "<div class='prow' id='pbtns'>"
        "<button class='pbtn active' data-days='14'>14D</button>"
        "<button class='pbtn' data-days='30'>30D</button>"
        "<button class='pbtn' data-days='60'>60D</button>"
        "<button class='pbtn' data-days='9999'>All</button>"
        "</div>"
        "<div class='cwrap'><canvas id='chart'></canvas></div>"
        "<div class='note' id='note'></div>"
        "</div>"
        "<div class='nbox'><h3>News events</h3><div id='newslist'></div></div>"
        f"<div class='footer'>NSE Bhavcopy + openchart + Yahoo Finance &middot; {generated_at}</div>"
        "<script>" + js + "</script>"
        "</body></html>"
    )


def deploy(html: str) -> str:
    token   = os.environ.get("NETLIFY_TOKEN", "")
    site_id = os.environ.get("NETLIFY_SITE_ID", "")
    if not token or not site_id:
        raise RuntimeError("NETLIFY_TOKEN or NETLIFY_SITE_ID not set")

    # _headers tells Netlify to serve index.html as text/html
    # Without this, the ZIP deploy API defaults to text/plain
    headers_file = """/index.html
  Content-Type: text/html; charset=UTF-8
  Cache-Control: no-cache, no-store, must-revalidate

/*
  Content-Type: text/html; charset=UTF-8
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html.encode("utf-8"))
        zf.writestr("_headers",   headers_file.encode("utf-8"))
    buf.seek(0)

    resp = req.post(
        f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
        data=buf.read(), timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Netlify {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    url  = data.get("ssl_url") or data.get("url") or f"https://{site_id}"
    log.info(f"Deployed -> {url}")
    return url
