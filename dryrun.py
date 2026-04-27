"""
DRY RUN — investment-bot
Simulates yfinance price data and generates the exact chart + caption
that would be sent to Telegram every morning.
No API keys or network needed.
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# ── Simulated price engine (deterministic, mirrors real market behaviour) ─────
def sim_prices(start_price, n_days, annual_drift, annual_vol, seed):
    rng = np.random.default_rng(seed)
    dt  = 1 / 252
    log_returns = (annual_drift - 0.5 * annual_vol**2) * dt + \
                  annual_vol * math.sqrt(dt) * rng.standard_normal(n_days)
    prices = start_price * np.exp(np.cumsum(np.insert(log_returns, 0, 0)))
    return prices.tolist()

def rebase(prices):
    base = prices[0]
    return [round(p / base * 100, 2) for p in prices]

def pct(rb):
    return round(rb[-1] - 100, 2) if rb else 0.0

def date_range(start_str, n):
    start = datetime.strptime(start_str, "%Y-%m-%d").date()
    return [start + timedelta(days=i) for i in range(n + 1)]

# ── Recommendation data ───────────────────────────────────────────────────────
TODAY = datetime.now().date()

RECS = [
    dict(label="TITAN",      name="Titan Company",       buy_date="2026-03-13",
         buy_low=4133.0, buy_high=4134.0, target=None,  type_="Positional",
         drift=0.14, vol=0.22, seed=42),
    dict(label="HAPPSTMNDS", name="Happiest Minds",       buy_date="2026-04-16",
         buy_low=383.5,  buy_high=385.0,  target=600.0, type_="Medium Term",
         drift=0.18, vol=0.28, seed=7),
    dict(label="HDFCPVTBAN", name="HDFC Pvt Bank ETF",    buy_date="2026-04-22",
         buy_low=27.7,   buy_high=27.8,   target=None,  type_="Positional",
         drift=0.11, vol=0.18, seed=13),
    dict(label="RELIANCE",   name="Reliance Industries",  buy_date="2026-04-23",
         buy_low=1353.0, buy_high=1354.0, target=None,  type_="Positional",
         drift=0.12, vol=0.20, seed=99),
]

NEWS = [
    dict(date="2026-03-15", symbol="TITAN",      text="Q3 jewellery revenue beats estimates",        impact="pos"),
    dict(date="2026-03-28", symbol="TITAN",      text="Gold prices hit record high",                 impact="neu"),
    dict(date="2026-04-10", symbol="TITAN",      text="Fastrack launch; analyst upgrades to Buy",    impact="pos"),
    dict(date="2026-04-17", symbol="HAPPSTMNDS", text="Mixed IT sector Q4 outlook",                  impact="neu"),
    dict(date="2026-04-22", symbol="ALL",        text="Markets rally on RBI rate cut expectations",  impact="pos"),
    dict(date="2026-04-23", symbol="RELIANCE",   text="AGM announced; JioMart expansion",            impact="pos"),
    dict(date="2026-04-24", symbol="HDFCPVTBAN", text="HDFC Bank Q4: NIM pressure but AQ improves", impact="neu"),
]

# ── Build per-rec data ────────────────────────────────────────────────────────
NIFTY_DRIFT, NIFTY_VOL   = 0.10, 0.13
SENSEX_DRIFT, SENSEX_VOL = 0.09, 0.12

recs_data = []
for r in RECS:
    buy_dt    = datetime.strptime(r["buy_date"], "%Y-%m-%d").date()
    n_days    = (TODAY - buy_dt).days
    dates     = date_range(r["buy_date"], n_days)

    stock_p   = sim_prices(r["buy_low"],  n_days, r["drift"],      r["vol"],       r["seed"])
    nifty_p   = sim_prices(100,           n_days, NIFTY_DRIFT,     NIFTY_VOL,      r["seed"] + 1000)
    sensex_p  = sim_prices(100,           n_days, SENSEX_DRIFT,    SENSEX_VOL,     r["seed"] + 2000)

    relevant_news = [ev for ev in NEWS if ev["symbol"] in (r["label"], "ALL")]

    recs_data.append(dict(
        label=r["label"], name=r["name"], buy_date=r["buy_date"],
        buy_low=r["buy_low"], type_=r["type_"], target=r["target"],
        dates=dates,
        stock_rb=rebase(stock_p),
        nifty_rb=rebase(nifty_p),
        sensex_rb=rebase(sensex_p),
        news=relevant_news,
    ))

# ── Chart ─────────────────────────────────────────────────────────────────────
C = dict(
    stock="#378ADD", nifty="#1D9E75", sensex="#D85A30",
    buy="#F0997B", bg="#FFFFFF", grid="#F0EEE8",
    text="#2C2C2A", muted="#888780",
    pos="#3B6D11", neu="#888780", neg="#A32D2D",
)
IMPACT = {"pos": C["pos"], "neu": C["neu"], "neg": C["neg"]}

n = len(recs_data)
fig, axes = plt.subplots(n, 1, figsize=(11, 3.8 * n), facecolor=C["bg"])
if n == 1:
    axes = [axes]

fig.suptitle(
    f"📊 Portfolio Update — {TODAY.strftime('%d %b %Y')}  |  Advisor: +91 877 990 0557",
    fontsize=12, fontweight="bold", color=C["text"], y=1.002,
)

sign = lambda v: "+" if v >= 0 else ""

for ax, rd in zip(axes, recs_data):
    ax.set_facecolor(C["bg"])
    for sp in ax.spines.values():
        sp.set_edgecolor(C["grid"])
    ax.tick_params(colors=C["muted"], labelsize=8)
    ax.yaxis.grid(True, color=C["grid"], lw=0.7, zorder=0)
    ax.set_axisbelow(True)

    dates  = rd["dates"]
    s_rb   = rd["stock_rb"]
    n_rb   = rd["nifty_rb"]
    x_rb   = rd["sensex_rb"]
    min_l  = min(len(dates), len(s_rb), len(n_rb), len(x_rb))
    dates, s_rb, n_rb, x_rb = dates[:min_l], s_rb[:min_l], n_rb[:min_l], x_rb[:min_l]

    ax.plot(dates, s_rb, color=C["stock"],  lw=2,   label=rd["label"],   zorder=3)
    ax.plot(dates, n_rb, color=C["nifty"],  lw=1.3, ls="--", label="Nifty 50",   zorder=2)
    ax.plot(dates, x_rb, color=C["sensex"], lw=1.3, ls=":",  label="Sensex",     zorder=2)

    # Shaded alpha region
    ax.fill_between(dates, s_rb, n_rb,
                    where=[s >= nn for s, nn in zip(s_rb, n_rb)],
                    alpha=0.09, color=C["stock"],  zorder=1)
    ax.fill_between(dates, s_rb, n_rb,
                    where=[s <  nn for s, nn in zip(s_rb, n_rb)],
                    alpha=0.09, color=C["sensex"], zorder=1)

    # Buy-date vertical line + badge
    buy_dt = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
    ymin, ymax = ax.get_ylim()
    ax.axvline(buy_dt, color=C["buy"], lw=1.8, ls="--", zorder=4)
    ax.text(buy_dt, max(s_rb) * 0.995,
            f"  Buy ₹{rd['buy_low']}", fontsize=7.5,
            color=C["buy"], va="top", fontweight="bold", zorder=5)

    # Target line
    if rd["target"]:
        target_pct = rd["target"] / rd["buy_low"] * 100
        ax.axhline(target_pct, color="#9B59B6", lw=1, ls=(0, (4,3)), alpha=0.7, zorder=2)
        ax.text(dates[-1], target_pct + 0.3, f"  Target {target_pct:.0f}%",
                fontsize=7, color="#9B59B6", va="bottom", zorder=5)

    # News dots + mini labels
    for ev in rd["news"]:
        ev_d = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        if ev_d in dates:
            idx = dates.index(ev_d)
            col = IMPACT.get(ev["impact"], C["neu"])
            ax.scatter(ev_d, s_rb[idx], color=col, s=55, zorder=6,
                       edgecolors="white", linewidths=0.9)
            short = ev["text"][:36] + ("…" if len(ev["text"]) > 36 else "")
            ax.annotate(short, (ev_d, s_rb[idx]),
                        xytext=(5, 7), textcoords="offset points",
                        fontsize=6.2, color=col, rotation=18, zorder=7)

    # Right-edge % labels
    for val, col in [(s_rb[-1], C["stock"]), (n_rb[-1], C["nifty"]), (x_rb[-1], C["sensex"])]:
        ax.text(1.005, val, f"{sign(val-100)}{val-100:.1f}%",
                transform=ax.get_yaxis_transform(),
                fontsize=7.5, color=col, va="center", fontweight="bold")

    # Subtitle / title
    s_p  = pct(s_rb); n_p = pct(n_rb); x_p = pct(x_rb)
    al   = round(s_p - n_p, 2)
    days = (TODAY - buy_dt).days
    al_col = C["pos"] if al >= 0 else C["neg"]
    title = (f"{rd['label']}  ·  {rd['name']}  ·  {days}d held  ·  "
             f"Alpha vs Nifty: {sign(al)}{al}%")
    ax.set_title(title, fontsize=9, color=C["text"], loc="left", pad=5)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    fig.autofmt_xdate(rotation=30, ha="right")

    leg = ax.legend(fontsize=7.5, loc="upper left", framealpha=0.85,
                    edgecolor=C["grid"], handlelength=1.8)
    leg.get_frame().set_linewidth(0.5)

plt.tight_layout(rect=[0, 0, 0.94, 0.99], h_pad=2.5)
out = Path("/home/claude/investment-bot/charts/dryrun_summary.png")
out.parent.mkdir(exist_ok=True)
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=C["bg"])
plt.close(fig)
print(f"✅ Chart saved → {out}")

# ── Caption preview ───────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TELEGRAM MESSAGE PREVIEW")
print("="*60)
lines = [f"📈 *Portfolio Summary — {TODAY.strftime('%d %b %Y')}*\n"]
for rd in recs_data:
    s_p = pct(rd["stock_rb"]); n_p = pct(rd["nifty_rb"]); x_p = pct(rd["sensex_rb"])
    al  = round(s_p - n_p, 2)
    buy_dt = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
    days   = (TODAY - buy_dt).days
    em     = "🟢" if s_p >= 0 else "🔴"
    lines.append(
        f"{em} *{rd['label']}* ({rd['type_']} · {days}d)\n"
        f"   Stock : {'+' if s_p>=0 else ''}{s_p}%   Nifty : {'+' if n_p>=0 else ''}{n_p}%   Sensex: {'+' if x_p>=0 else ''}{x_p}%\n"
        f"   Alpha vs Nifty : {'+' if al>=0 else ''}{al}%"
    )
    if rd["target"]:
        tgt_pct = round((rd["target"] / rd["buy_low"] - 1) * 100, 1)
        lines.append(f"   Target : ₹{rd['target']}  ({'+' if tgt_pct>=0 else ''}{tgt_pct}% upside from buy)")
    lines.append("")
lines.append("🔍 Full charts & news → https://your-detail-app.netlify.app")
print("\n".join(lines))

print("\n" + "="*60)
print("PERFORMANCE TABLE")
print("="*60)
print(f"{'Stock':<14} {'Days':>5} {'Stock%':>8} {'Nifty%':>8} {'Sensex%':>9} {'Alpha%':>8}")
print("-"*57)
for rd in recs_data:
    s_p = pct(rd["stock_rb"]); n_p = pct(rd["nifty_rb"]); x_p = pct(rd["sensex_rb"])
    al  = round(s_p - n_p, 2)
    buy_dt = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
    days   = (TODAY - buy_dt).days
    print(f"{rd['label']:<14} {days:>5} {s_p:>+8.2f} {n_p:>+8.2f} {x_p:>+9.2f} {al:>+8.2f}")
print("="*57)
print("\n✅ Dry run complete — no network or API keys used.")
