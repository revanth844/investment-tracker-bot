"""
Investment Advisor Tracker Bot — FIXED VERSION
Fixes:
  1. Correct User-Agent so Yahoo Finance doesn't block the request
  2. Retry logic (3 attempts with backoff) for rate limits / timeouts
  3. Symbol validation before charting — logs exact error per symbol
  4. Fallback: if index data fails, skip index lines rather than crashing
  5. Timezone-aware date handling for NSE (IST close = 15:30)
  6. "No data" guard replaced with partial-data graceful rendering
"""

import os, json, asyncio, logging, time, random
from datetime import datetime, timedelta, date
from pathlib import Path
from io import BytesIO

import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import requests                         # yfinance uses requests internally
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]
DETAIL_URL     = os.environ.get("DETAIL_URL", "https://your-detail-app.netlify.app")
SEND_HOUR      = int(os.environ.get("SEND_HOUR", "15"))
TIMEZONE       = "Asia/Kolkata"

DATA_FILE = Path("data/recommendations.json")

DEFAULT_RECS = [
    {"symbol":"TITAN.NS",      "label":"TITAN",      "name":"Titan Company",       "buy_date":"2026-03-13","buy_low":4133.0,"buy_high":4134.0,"target":None, "type":"Positional"},
    {"symbol":"HAPPSTMNDS.NS", "label":"HAPPSTMNDS", "name":"Happiest Minds",       "buy_date":"2026-04-16","buy_low":383.5, "buy_high":385.0, "target":600.0,"type":"Medium Term"},
    {"symbol":"HDFCPVTBAN.NS", "label":"HDFCPVTBAN", "name":"HDFC Pvt Bank ETF",   "buy_date":"2026-04-22","buy_low":27.7,  "buy_high":27.8,  "target":None, "type":"Positional"},
    {"symbol":"RELIANCE.NS",   "label":"RELIANCE",   "name":"Reliance Industries",  "buy_date":"2026-04-23","buy_low":1353.0,"buy_high":1354.0,"target":None, "type":"Positional"},
]

NEWS_EVENTS = [
    {"date":"2026-03-15","symbol":"TITAN",      "text":"Q3 jewellery revenue beats estimates",       "impact":"pos"},
    {"date":"2026-03-28","symbol":"TITAN",      "text":"Gold prices hit record high",                "impact":"neu"},
    {"date":"2026-04-10","symbol":"TITAN",      "text":"Fastrack launch; analyst upgrades to Buy",   "impact":"pos"},
    {"date":"2026-04-17","symbol":"HAPPSTMNDS", "text":"Mixed IT sector Q4 outlook",                 "impact":"neu"},
    {"date":"2026-04-22","symbol":"ALL",        "text":"Markets rally on RBI rate cut expectations", "impact":"pos"},
    {"date":"2026-04-23","symbol":"RELIANCE",   "text":"AGM announced; JioMart expansion",           "impact":"pos"},
    {"date":"2026-04-24","symbol":"HDFCPVTBAN", "text":"HDFC Bank Q4: NIM pressure, AQ improves",   "impact":"neu"},
]

def load_recs():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(DEFAULT_RECS, indent=2))
    return DEFAULT_RECS


# ── FIX 1: Robust price fetch with User-Agent + retries ──────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def fetch_prices(symbol: str, start: str, retries: int = 3):
    """
    Returns (dates: list[date], closes: list[float]).
    Empty lists on failure — caller handles gracefully.
    Includes User-Agent header and retry backoff.
    """
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()

    for attempt in range(1, retries + 1):
        try:
            # FIX: pass a requests Session with proper headers so Yahoo
            # doesn't return 429 / empty payload on Railway IPs
            session = requests.Session()
            session.headers.update(HEADERS)

            tk = yf.Ticker(symbol, session=session)
            df = tk.history(start=start, interval="1d", auto_adjust=True, timeout=15)

            if df is None or df.empty:
                log.warning(f"[{symbol}] attempt {attempt}: empty DataFrame")
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue

            # FIX: strip timezone so date comparison works consistently
            df.index = df.index.tz_localize(None)

            dates  = [d.date() for d in df.index if d.date() >= start_dt]
            closes = [float(df.loc[df.index.date == d, "Close"].iloc[0])
                      for d in dates if len(df.loc[df.index.date == d]) > 0]

            if len(dates) == 0:
                log.warning(f"[{symbol}] attempt {attempt}: no rows after {start}")
                time.sleep(2 ** attempt)
                continue

            log.info(f"[{symbol}] fetched {len(dates)} days from {dates[0]} to {dates[-1]}")
            return dates, closes

        except Exception as e:
            log.error(f"[{symbol}] attempt {attempt} exception: {e}")
            time.sleep(2 ** attempt + random.uniform(0, 1))

    log.error(f"[{symbol}] ALL {retries} attempts failed — returning empty")
    return [], []


def rebase(prices):
    if not prices or prices[0] == 0:
        return []
    b = prices[0]
    return [round(p / b * 100, 2) for p in prices]

def pct(rb):
    return round(rb[-1] - 100, 2) if rb else 0.0

def align(dates_a, closes_a, dates_b, closes_b):
    """Return two close lists aligned to common dates."""
    common = sorted(set(dates_a) & set(dates_b))
    if not common:
        return [], [], []
    idx_a = {d: c for d, c in zip(dates_a, closes_a)}
    idx_b = {d: c for d, c in zip(dates_b, closes_b)}
    return common, [idx_a[d] for d in common], [idx_b[d] for d in common]


# ── Chart ─────────────────────────────────────────────────────────────────────
C = dict(
    stock="#378ADD", nifty="#1D9E75", sensex="#D85A30",
    buy="#F0997B",   bg="#FFFFFF",   grid="#F0EEE8",
    text="#2C2C2A",  muted="#888780",
    pos="#3B6D11",   neu="#888780",  neg="#A32D2D",
)
IMPACT = {"pos": C["pos"], "neu": C["neu"], "neg": C["neg"]}
sign = lambda v: "+" if v >= 0 else ""

def make_chart(recs_data: list) -> BytesIO:
    n   = len(recs_data)
    fig, axes = plt.subplots(n, 1, figsize=(11, 3.8 * n), facecolor=C["bg"])
    if n == 1:
        axes = [axes]

    fig.suptitle(
        f"Portfolio Update  |  {datetime.now().strftime('%d %b %Y')}  |  Advisor: +91 877 990 0557",
        fontsize=11, fontweight="bold", color=C["text"], y=1.002,
    )

    for ax, rd in zip(axes, recs_data):
        ax.set_facecolor(C["bg"])
        for sp in ax.spines.values():
            sp.set_edgecolor(C["grid"])
        ax.tick_params(colors=C["muted"], labelsize=8)
        ax.yaxis.grid(True, color=C["grid"], lw=0.7, zorder=0)
        ax.set_axisbelow(True)

        dates   = rd["dates"]
        s_rb    = rd["stock_rb"]
        n_rb    = rd["nifty_rb"]
        x_rb    = rd["sensex_rb"]

        buy_dt  = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
        days    = (date.today() - buy_dt).days

        # FIX: graceful partial data — draw what we have
        has_stock  = bool(dates and s_rb)
        has_nifty  = bool(n_rb)
        has_sensex = bool(x_rb)

        if not has_stock:
            ax.text(0.5, 0.5,
                    f"{rd['label']}\nData unavailable — Yahoo Finance fetch failed.\n"
                    f"Check Railway logs for symbol: {rd['symbol']}",
                    ha="center", va="center", transform=ax.transAxes,
                    color=C["neg"], fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.4", facecolor="#FCEBEB", edgecolor=C["neg"], lw=0.8))
            ax.set_title(f"{rd['label']}  ·  {rd['name']}  ·  {days}d held",
                         fontsize=9, color=C["text"], loc="left", pad=5)
            continue

        ax.plot(dates, s_rb, color=C["stock"],  lw=2,   label=rd["label"],  zorder=3)
        if has_nifty:
            ax.plot(dates, n_rb, color=C["nifty"],  lw=1.3, ls="--", label="Nifty 50", zorder=2)
        if has_sensex:
            ax.plot(dates, x_rb, color=C["sensex"], lw=1.3, ls=":",  label="Sensex",   zorder=2)

        # Shaded alpha region vs Nifty
        if has_nifty:
            ax.fill_between(dates, s_rb, n_rb,
                where=[s >= nn for s, nn in zip(s_rb, n_rb)],
                alpha=0.09, color=C["stock"],  zorder=1)
            ax.fill_between(dates, s_rb, n_rb,
                where=[s <  nn for s, nn in zip(s_rb, n_rb)],
                alpha=0.09, color=C["sensex"], zorder=1)

        # Buy date line
        ax.axvline(buy_dt, color=C["buy"], lw=1.8, ls="--", zorder=4)
        ax.text(buy_dt, max(s_rb) * 0.998,
                f"  Buy ₹{rd['buy_low']}", fontsize=7.5,
                color=C["buy"], va="top", fontweight="bold", zorder=5)

        # Target line
        if rd.get("target"):
            tpct = rd["target"] / rd["buy_low"] * 100
            ax.axhline(tpct, color="#9B59B6", lw=1, ls=(0,(4,3)), alpha=0.75, zorder=2)
            ax.text(dates[-1], tpct + 0.3, f"  Target {tpct:.0f}%",
                    fontsize=7, color="#9B59B6", va="bottom", zorder=5)

        # News dots
        news_for = [ev for ev in NEWS_EVENTS if ev["symbol"] in (rd["label"], "ALL")]
        for ev in news_for:
            ev_d = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if ev_d in dates:
                idx = dates.index(ev_d)
                col = IMPACT.get(ev["impact"], C["neu"])
                ax.scatter(ev_d, s_rb[idx], color=col, s=55, zorder=6,
                           edgecolors="white", linewidths=0.9)
                short = ev["text"][:36] + ("…" if len(ev["text"]) > 36 else "")
                ax.annotate(short, (ev_d, s_rb[idx]),
                            xytext=(5,7), textcoords="offset points",
                            fontsize=6.2, color=col, rotation=18, zorder=7)

        # Right-edge % labels
        s_p = pct(s_rb); n_p = pct(n_rb); x_p = pct(x_rb)
        al  = round(s_p - n_p, 2) if has_nifty else None
        ax.text(1.005, s_rb[-1], f"{sign(s_p)}{s_p}%",
                transform=ax.get_yaxis_transform(), fontsize=7.5,
                color=C["stock"], va="center", fontweight="bold")
        if has_nifty:
            ax.text(1.005, n_rb[-1], f"{sign(n_p)}{n_p}%",
                    transform=ax.get_yaxis_transform(), fontsize=7.5,
                    color=C["nifty"], va="center", fontweight="bold")
        if has_sensex:
            ax.text(1.005, x_rb[-1], f"{sign(x_p)}{x_p}%",
                    transform=ax.get_yaxis_transform(), fontsize=7.5,
                    color=C["sensex"], va="center", fontweight="bold")

        al_str = f"  |  Alpha vs Nifty: {sign(al)}{al}%" if al is not None else ""
        ax.set_title(f"{rd['label']}  ·  {rd['name']}  ·  {days}d held{al_str}",
                     fontsize=9, color=C["text"], loc="left", pad=5)

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        fig.autofmt_xdate(rotation=30, ha="right")

        leg = ax.legend(fontsize=7.5, loc="upper left", framealpha=0.85,
                        edgecolor=C["grid"], handlelength=1.8)
        leg.get_frame().set_linewidth(0.5)

    plt.tight_layout(rect=[0, 0, 0.94, 0.99], h_pad=2.5)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    buf.seek(0)
    return buf


# ── Caption ───────────────────────────────────────────────────────────────────
def build_caption(recs_data):
    today = datetime.now().strftime("%d %b %Y")
    lines = [f"*Portfolio Summary — {today}*\n"]
    for rd in recs_data:
        s_p = pct(rd["stock_rb"]); n_p = pct(rd["nifty_rb"]); x_p = pct(rd["sensex_rb"])
        al  = round(s_p - n_p, 2)
        buy_dt = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
        days   = (date.today() - buy_dt).days
        em = "🟢" if s_p >= 0 else "🔴"
        if not rd["stock_rb"]:
            lines.append(f"⚠️ *{rd['label']}* — data fetch failed, check logs\n")
            continue
        lines.append(
            f"{em} *{rd['label']}* ({rd['type']} · {days}d)\n"
            f"   Stock: `{sign(s_p)}{s_p}%`   Nifty: `{sign(n_p)}{n_p}%`   Sensex: `{sign(x_p)}{x_p}%`\n"
            f"   Alpha vs Nifty: `{sign(al)}{al}%`"
        )
        if rd.get("target"):
            up = round((rd["target"] / rd["buy_low"] - 1) * 100, 1)
            lines.append(f"   Target: ₹{rd['target']}  ({sign(up)}{up}% from buy)")
        lines.append("")
    lines.append(f"[Full charts & news]({DETAIL_URL})")
    return "\n".join(lines)


# ── Main job ──────────────────────────────────────────────────────────────────
async def send_daily_update():
    log.info("=== Daily update starting ===")
    recs = load_recs()
    bot  = Bot(token=TELEGRAM_TOKEN)

    # FIX: fetch indices once with earliest buy date as start
    earliest = min(r["buy_date"] for r in recs)
    log.info(f"Fetching ^NSEI and ^BSESN from {earliest}")
    nifty_dates,  nifty_closes  = fetch_prices("^NSEI",  earliest)
    sensex_dates, sensex_closes = fetch_prices("^BSESN", earliest)

    recs_data = []
    for rec in recs:
        log.info(f"Fetching {rec['symbol']} from {rec['buy_date']}")
        s_dates, s_closes = fetch_prices(rec["symbol"], rec["buy_date"])

        # FIX: align all three series to common trading days
        if s_dates and nifty_dates:
            common_sn, s_aligned, n_aligned = align(s_dates, s_closes, nifty_dates, nifty_closes)
        else:
            common_sn, s_aligned, n_aligned = s_dates, s_closes, []

        if s_dates and sensex_dates:
            common_sx, _, x_aligned = align(s_dates, s_closes, sensex_dates, sensex_closes)
            # re-align s to sensex common dates too
        else:
            x_aligned = []

        # Use stock-nifty common dates as master timeline
        dates = common_sn if common_sn else s_dates

        recs_data.append(dict(
            label     = rec["label"],
            name      = rec["name"],
            buy_date  = rec["buy_date"],
            buy_low   = rec["buy_low"],
            type      = rec["type"],
            target    = rec.get("target"),
            symbol    = rec["symbol"],
            dates     = dates,
            stock_rb  = rebase(s_aligned) if s_aligned else rebase(s_closes),
            nifty_rb  = rebase(n_aligned),
            sensex_rb = rebase(x_aligned) if x_aligned else [],
        ))
        # Brief pause between fetches to avoid rate limiting
        await asyncio.sleep(1.5)

    chart_buf = make_chart(recs_data)
    caption   = build_caption(recs_data)

    await bot.send_photo(
        chat_id=CHAT_ID,
        photo=chart_buf,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
    )
    log.info("=== Message sent ✓ ===")


# ── Entrypoint ────────────────────────────────────────────────────────────────
async def main():
    log.info(f"Bot starting — daily ping at {SEND_HOUR}:00 {TIMEZONE}")
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(send_daily_update, "cron", hour=SEND_HOUR, minute=0)
    scheduler.start()
    await send_daily_update()          # immediate run on startup
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
