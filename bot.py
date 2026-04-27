"""
Investment Advisor Tracker Bot
Daily Telegram summary with chart + news for tracked recommendations.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import numpy as np
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]          # your personal chat/group id
DETAIL_URL     = os.environ.get("DETAIL_URL", "https://your-detail-app.netlify.app")
SEND_HOUR      = int(os.environ.get("SEND_HOUR", "8"))   # 8 AM IST daily
TIMEZONE       = "Asia/Kolkata"

DATA_FILE = Path("data/recommendations.json")

# ── Recommendations ───────────────────────────────────────────────────────────
DEFAULT_RECS = [
    {
        "symbol":    "TITAN.NS",
        "label":     "TITAN",
        "name":      "Titan Company",
        "buy_date":  "2026-03-13",
        "buy_low":   4133.0,
        "buy_high":  4134.0,
        "target":    None,
        "type":      "Positional",
    },
    {
        "symbol":    "HAPPSTMNDS.NS",
        "label":     "HAPPSTMNDS",
        "name":      "Happiest Minds",
        "buy_date":  "2026-04-16",
        "buy_low":   383.5,
        "buy_high":  385.0,
        "target":    600.0,
        "type":      "Medium Term",
    },
    {
        "symbol":    "HDFCPVTBAN.NS",
        "label":     "HDFCPVTBAN",
        "name":      "HDFC Pvt Bank ETF",
        "buy_date":  "2026-04-22",
        "buy_low":   27.7,
        "buy_high":  27.8,
        "target":    None,
        "type":      "Positional",
    },
    {
        "symbol":    "RELIANCE.NS",
        "label":     "RELIANCE",
        "name":      "Reliance Industries",
        "buy_date":  "2026-04-23",
        "buy_low":   1353.0,
        "buy_high":  1354.0,
        "target":    None,
        "type":      "Positional",
    },
]

NEWS_EVENTS = [
    {"date": "2026-03-15", "symbol": "TITAN",      "text": "Q3 jewellery revenue beats estimates; wedding season demand strong", "impact": "pos"},
    {"date": "2026-03-28", "symbol": "TITAN",      "text": "Gold prices hit record — mixed impact on margins vs demand",         "impact": "neu"},
    {"date": "2026-04-10", "symbol": "TITAN",      "text": "Fastrack launch; analyst upgrades to Buy",                           "impact": "pos"},
    {"date": "2026-04-17", "symbol": "HAPPSTMNDS", "text": "Q4 IT sector outlook — mixed signals on US client spend",            "impact": "neu"},
    {"date": "2026-04-22", "symbol": "ALL",        "text": "India markets rally on RBI rate cut expectations",                   "impact": "pos"},
    {"date": "2026-04-23", "symbol": "RELIANCE",   "text": "AGM date announced; JioMart expansion boosts sentiment",             "impact": "pos"},
    {"date": "2026-04-24", "symbol": "HDFCPVTBAN", "text": "HDFC Bank Q4: NIM pressure but asset quality improves",             "impact": "neu"},
]

def load_recs():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(DEFAULT_RECS, indent=2))
    return DEFAULT_RECS

def save_recs(recs):
    DATA_FILE.write_text(json.dumps(recs, indent=2))


# ── Price fetching ────────────────────────────────────────────────────────────
def fetch_prices(symbol: str, start: str) -> tuple[list, list]:
    """Returns (dates, closes) lists from start date to today."""
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(start=start, interval="1d")
        if df.empty:
            return [], []
        df.index = df.index.tz_localize(None)
        dates  = [d.date() for d in df.index]
        closes = df["Close"].tolist()
        return dates, closes
    except Exception as e:
        log.error(f"Failed fetching {symbol}: {e}")
        return [], []

def rebase(prices):
    """Rebase price list to 100 at first point."""
    if not prices:
        return []
    base = prices[0]
    return [round((p / base) * 100, 2) for p in prices]

def pct(rebased_list):
    if not rebased_list:
        return 0.0
    return round(rebased_list[-1] - 100, 2)


# ── Chart generation ──────────────────────────────────────────────────────────
COLORS = {
    "stock":  "#378ADD",
    "nifty":  "#1D9E75",
    "sensex": "#D85A30",
    "buy":    "#F0997B",
    "news_pos": "#3B6D11",
    "news_neu": "#888780",
    "news_neg": "#A32D2D",
    "bg":     "#FFFFFF",
    "grid":   "#F0EEE8",
    "text":   "#2C2C2A",
    "muted":  "#888780",
}

IMPACT_COLOR = {"pos": COLORS["news_pos"], "neg": COLORS["news_neg"], "neu": COLORS["news_neu"]}

def make_chart(recs_data: list) -> str:
    """
    recs_data: list of dicts with keys:
      label, buy_date, stock_dates, stock_rb, nifty_rb, sensex_rb, news
    Returns path to saved PNG.
    """
    n = len(recs_data)
    fig, axes = plt.subplots(n, 1, figsize=(10, 3.6 * n), facecolor=COLORS["bg"])
    if n == 1:
        axes = [axes]

    fig.suptitle(
        f"📊 Portfolio Update — {datetime.now().strftime('%d %b %Y')}",
        fontsize=13, fontweight="bold", color=COLORS["text"], y=1.0
    )

    for ax, rd in zip(axes, recs_data):
        ax.set_facecolor(COLORS["bg"])
        ax.tick_params(colors=COLORS["muted"], labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(COLORS["grid"])
        ax.yaxis.grid(True, color=COLORS["grid"], linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)

        dates      = rd["stock_dates"]
        stock_rb   = rd["stock_rb"]
        nifty_rb   = rd["nifty_rb"]
        sensex_rb  = rd["sensex_rb"]

        if not dates:
            ax.text(0.5, 0.5, f"{rd['label']}\nNo data available",
                    ha="center", va="center", transform=ax.transAxes,
                    color=COLORS["muted"], fontsize=10)
            continue

        # Plot lines
        ax.plot(dates, stock_rb,  color=COLORS["stock"],  lw=2,   label=rd["label"], zorder=3)
        ax.plot(dates, nifty_rb,  color=COLORS["nifty"],  lw=1.2, linestyle="--", label="Nifty 50", zorder=2)
        ax.plot(dates, sensex_rb, color=COLORS["sensex"], lw=1.2, linestyle=":",  label="Sensex",   zorder=2)

        # Buy date vertical line
        buy_dt = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
        ax.axvline(buy_dt, color=COLORS["buy"], lw=1.5, linestyle="--", zorder=4)
        ax.text(buy_dt, ax.get_ylim()[1] if ax.get_ylim()[1] > 95 else 100,
                f" Buy ₹{rd['buy_low']}", fontsize=7, color=COLORS["buy"],
                va="top", zorder=5)

        # Shade area between stock and nifty
        min_len = min(len(dates), len(stock_rb), len(nifty_rb))
        ax.fill_between(dates[:min_len], stock_rb[:min_len], nifty_rb[:min_len],
                        where=[s >= n for s, n in zip(stock_rb[:min_len], nifty_rb[:min_len])],
                        alpha=0.08, color=COLORS["stock"], zorder=1)
        ax.fill_between(dates[:min_len], stock_rb[:min_len], nifty_rb[:min_len],
                        where=[s < n for s, n in zip(stock_rb[:min_len], nifty_rb[:min_len])],
                        alpha=0.08, color=COLORS["sensex"], zorder=1)

        # News event markers
        for ev in rd["news"]:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if ev_date in dates:
                idx = dates.index(ev_date)
                if idx < len(stock_rb):
                    col = IMPACT_COLOR.get(ev["impact"], COLORS["news_neu"])
                    ax.scatter(ev_date, stock_rb[idx], color=col, s=40, zorder=6,
                               edgecolors="white", linewidths=0.8)
                    # Short label rotated
                    short = ev["text"][:32] + ("…" if len(ev["text"]) > 32 else "")
                    ax.annotate(short, (ev_date, stock_rb[idx]),
                                fontsize=6, color=col,
                                xytext=(4, 6), textcoords="offset points",
                                rotation=20, zorder=7)

        # % labels at right edge
        s_pct  = pct(stock_rb)
        n_pct  = pct(nifty_rb)
        x_pct  = pct(sensex_rb)
        alpha_ = round(s_pct - n_pct, 2)
        sign   = lambda v: ("+" if v >= 0 else "")

        ax.text(1.01, stock_rb[-1],  f"{sign(s_pct)}{s_pct}%",  transform=ax.get_yaxis_transform(),
                fontsize=8, color=COLORS["stock"],  va="center")
        ax.text(1.01, nifty_rb[-1],  f"{sign(n_pct)}{n_pct}%",  transform=ax.get_yaxis_transform(),
                fontsize=8, color=COLORS["nifty"],  va="center")
        ax.text(1.01, sensex_rb[-1], f"{sign(x_pct)}{x_pct}%",  transform=ax.get_yaxis_transform(),
                fontsize=8, color=COLORS["sensex"], va="center")

        # Title bar
        days_held = (datetime.now().date() - buy_dt).days
        tag_color = "#EAF3DE" if s_pct >= 0 else "#FCEBEB"
        tag_fc    = COLORS["news_pos"] if s_pct >= 0 else COLORS["news_neg"]
        title_str = (f"{rd['label']}  ·  {rd['name']}  ·  {days_held}d held  ·  "
                     f"Alpha vs Nifty: {sign(alpha_)}{alpha_}%")
        ax.set_title(title_str, fontsize=9, color=COLORS["text"], loc="left", pad=6)

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        fig.autofmt_xdate(rotation=30, ha="right")

        legend = ax.legend(fontsize=7, loc="upper left", framealpha=0.8,
                           edgecolor=COLORS["grid"])
        legend.get_frame().set_linewidth(0.5)

    plt.tight_layout(rect=[0, 0, 0.92, 0.97])
    out = Path("charts/daily_summary.png")
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close(fig)
    log.info(f"Chart saved → {out}")
    return str(out)


# ── Telegram message ──────────────────────────────────────────────────────────
def build_caption(recs_data: list, detail_url: str) -> str:
    today = datetime.now().strftime("%d %b %Y")
    lines = [f"*📈 Portfolio Summary — {today}*\n"]

    for rd in recs_data:
        s  = pct(rd["stock_rb"])
        n  = pct(rd["nifty_rb"])
        x  = pct(rd["sensex_rb"])
        al = round(s - n, 2)
        sign  = lambda v: ("+" if v >= 0 else "")
        emoji = "🟢" if s >= 0 else "🔴"
        buy_dt = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
        days_held = (datetime.now().date() - buy_dt).days

        lines.append(
            f"{emoji} *{rd['label']}* ({rd['type']} · {days_held}d)\n"
            f"   Stock: `{sign(s)}{s}%`  Nifty: `{sign(n)}{n}%`  Sensex: `{sign(x)}{x}%`\n"
            f"   Alpha vs Nifty: `{sign(al)}{al}%`"
        )
        if rd.get("target"):
            lines.append(f"   Target: ₹{rd['target']}")
        lines.append("")

    lines.append(f"[🔍 Full charts & news]({detail_url})")
    return "\n".join(lines)


# ── Main job ──────────────────────────────────────────────────────────────────
async def send_daily_update():
    log.info("Running daily update job…")
    recs = load_recs()
    bot  = Bot(token=TELEGRAM_TOKEN)

    nifty_dates,  nifty_closes  = fetch_prices("^NSEI",  "2026-03-01")
    sensex_dates, sensex_closes = fetch_prices("^BSESN", "2026-03-01")

    recs_data = []
    for rec in recs:
        buy_date = rec["buy_date"]
        s_dates, s_closes = fetch_prices(rec["symbol"], buy_date)

        def slice_from(all_dates, all_closes, from_date_str):
            from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
            pairs = [(d, c) for d, c in zip(all_dates, all_closes) if d >= from_date]
            if not pairs:
                return [], []
            return zip(*pairs)

        n_dates_sl, n_closes_sl = slice_from(nifty_dates,  nifty_closes,  buy_date)
        x_dates_sl, x_closes_sl = slice_from(sensex_dates, sensex_closes, buy_date)

        n_dates_sl  = list(n_dates_sl)
        n_closes_sl = list(n_closes_sl)
        x_dates_sl  = list(x_dates_sl)
        x_closes_sl = list(x_closes_sl)

        # Align lengths to shortest series
        min_len = min(len(s_dates), len(n_dates_sl), len(x_dates_sl))
        s_dates     = s_dates[:min_len]
        s_closes    = s_closes[:min_len]
        n_closes_sl = n_closes_sl[:min_len]
        x_closes_sl = x_closes_sl[:min_len]

        relevant_news = [
            ev for ev in NEWS_EVENTS
            if ev["symbol"] in (rec["label"], "ALL")
        ]

        recs_data.append({
            "label":       rec["label"],
            "name":        rec["name"],
            "buy_date":    buy_date,
            "buy_low":     rec["buy_low"],
            "type":        rec["type"],
            "target":      rec.get("target"),
            "stock_dates": s_dates,
            "stock_rb":    rebase(s_closes),
            "nifty_rb":    rebase(n_closes_sl),
            "sensex_rb":   rebase(x_closes_sl),
            "news":        relevant_news,
        })

    chart_path = make_chart(recs_data)
    caption    = build_caption(recs_data, DETAIL_URL)

    with open(chart_path, "rb") as img:
        await bot.send_photo(
            chat_id=CHAT_ID,
            photo=img,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )
    log.info("Message sent ✓")


# ── Entrypoint ────────────────────────────────────────────────────────────────
async def main():
    log.info(f"Bot starting — will send at {SEND_HOUR}:00 {TIMEZONE} daily")
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(send_daily_update, "cron", hour=SEND_HOUR, minute=0)
    scheduler.start()

    # Send once immediately on startup so you can verify it works
    await send_daily_update()

    # Keep running
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
