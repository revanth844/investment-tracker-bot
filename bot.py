"""
Investment Advisor Tracker Bot — v3
Fixes:
  - Rate limiting: longer backoff (15s, 30s, 60s), rotating User-Agents,
    random jitter, 30s sleep between each symbol fetch
  - Telegram /add command to add new recommendations without editing code
  - Telegram /list command to see all tracked stocks
  - /remove command to stop tracking a stock
"""

import os, json, asyncio, logging, time, random, re
from datetime import datetime, date
from pathlib import Path
from io import BytesIO

import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests as req_lib
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes, ApplicationBuilder
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from netlify_deploy import build_html, deploy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
CHAT_ID         = os.environ["CHAT_ID"]
NETLIFY_TOKEN   = os.environ["NETLIFY_TOKEN"]
NETLIFY_SITE_ID = os.environ["NETLIFY_SITE_ID"]
SEND_HOUR       = int(os.environ.get("SEND_HOUR", "15"))
TIMEZONE        = "Asia/Kolkata"

DATA_FILE = Path("data/recommendations.json")
NEWS_FILE = Path("data/news_events.json")

DEFAULT_RECS = [
    {"symbol":"TITAN.NS",      "label":"TITAN",      "name":"Titan Company",      "buy_date":"2026-03-13","buy_low":4133.0,"buy_high":4134.0,"target":None, "type":"Positional"},
    {"symbol":"HAPPSTMNDS.NS", "label":"HAPPSTMNDS", "name":"Happiest Minds",      "buy_date":"2026-04-16","buy_low":383.5, "buy_high":385.0, "target":600.0,"type":"Medium Term"},
    {"symbol":"HDFCPVTBAN.NS", "label":"HDFCPVTBAN", "name":"HDFC Pvt Bank ETF",  "buy_date":"2026-04-22","buy_low":27.7,  "buy_high":27.8,  "target":None, "type":"Positional"},
    {"symbol":"RELIANCE.NS",   "label":"RELIANCE",   "name":"Reliance Industries", "buy_date":"2026-04-23","buy_low":1353.0,"buy_high":1354.0,"target":None, "type":"Positional"},
]

DEFAULT_NEWS = [
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

def save_recs(recs):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(recs, indent=2))

def load_news():
    if NEWS_FILE.exists():
        return json.loads(NEWS_FILE.read_text())
    NEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    NEWS_FILE.write_text(json.dumps(DEFAULT_NEWS, indent=2))
    return DEFAULT_NEWS

def save_news(news):
    NEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    NEWS_FILE.write_text(json.dumps(news, indent=2))


# ── Rate-limit-aware price fetching ──────────────────────────────────────────
# Rotate user agents to reduce fingerprinting
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# Backoff: wait 15s, 30s, 60s between retries (not 2s, 4s — that's too fast for Yahoo)
RETRY_WAITS = [15, 30, 60]

def fetch_prices(symbol: str, start: str, retries: int = 3):
    """
    Fetch daily closes from Yahoo Finance with rate-limit-aware retries.
    Returns (dates: list[date], closes: list[float]) or ([], []) on failure.
    """
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()

    for attempt in range(retries):
        wait = RETRY_WAITS[attempt] + random.uniform(0, 5)
        if attempt > 0:
            log.info(f"[{symbol}] waiting {wait:.0f}s before attempt {attempt+1}...")
            time.sleep(wait)
        try:
            session = req_lib.Session()
            session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

            tk = yf.Ticker(symbol, session=session)
            df = tk.history(start=start, interval="1d", auto_adjust=True, timeout=20)

            if df is None or df.empty:
                log.warning(f"[{symbol}] attempt {attempt+1}: empty response")
                continue

            df.index = df.index.tz_localize(None)
            dates  = [d.date() for d in df.index if d.date() >= start_dt]
            closes = [float(df.loc[df.index.date == d, "Close"].iloc[0]) for d in dates]

            if not dates:
                log.warning(f"[{symbol}] attempt {attempt+1}: no rows after {start}")
                continue

            log.info(f"[{symbol}] OK — {len(dates)} days ({dates[0]} to {dates[-1]})")
            return dates, closes

        except Exception as e:
            log.error(f"[{symbol}] attempt {attempt+1} failed: {e}")

    log.error(f"[{symbol}] all {retries} attempts failed")
    return [], []

def rebase(prices):
    if not prices or prices[0] == 0:
        return []
    b = prices[0]
    return [round(p / b * 100, 2) for p in prices]

def pct(rb):
    return round(rb[-1] - 100, 2) if rb else 0.0

def align(dates_a, closes_a, dates_b, closes_b):
    common = sorted(set(dates_a) & set(dates_b))
    if not common:
        return [], [], []
    ia = {d: c for d, c in zip(dates_a, closes_a)}
    ib = {d: c for d, c in zip(dates_b, closes_b)}
    return common, [ia[d] for d in common], [ib[d] for d in common]


# ── Matplotlib chart ──────────────────────────────────────────────────────────
C = dict(
    stock="#378ADD", nifty="#1D9E75", sensex="#D85A30",
    buy="#F0997B", bg="#FFFFFF", grid="#F0EEE8",
    text="#2C2C2A", muted="#888780",
    pos="#3B6D11", neu="#888780", neg="#A32D2D",
)
IMPACT = {"pos": C["pos"], "neu": C["neu"], "neg": C["neg"]}
sign = lambda v: "+" if v >= 0 else ""

def make_chart(recs_data: list, news_events: list) -> BytesIO:
    n = len(recs_data)
    fig, axes = plt.subplots(n, 1, figsize=(11, 3.8 * n), facecolor=C["bg"])
    if n == 1:
        axes = [axes]
    fig.suptitle(
        f"Portfolio Update  |  {datetime.now().strftime('%d %b %Y')}  |  Advisor: +91 877 990 0557",
        fontsize=11, fontweight="bold", color=C["text"], y=1.002,
    )
    for ax, rd in zip(axes, recs_data):
        ax.set_facecolor(C["bg"])
        for sp in ax.spines.values(): sp.set_edgecolor(C["grid"])
        ax.tick_params(colors=C["muted"], labelsize=8)
        ax.yaxis.grid(True, color=C["grid"], lw=0.7, zorder=0)
        ax.set_axisbelow(True)

        dates = rd["dates"]; s_rb = rd["stock_rb"]; n_rb = rd["nifty_rb"]; x_rb = rd["sensex_rb"]
        buy_dt = datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()
        days = (date.today() - buy_dt).days

        if not (dates and s_rb):
            ax.text(0.5, 0.5,
                f"{rd['label']} — fetch failed (rate limited)\nWill retry at next scheduled run",
                ha="center", va="center", transform=ax.transAxes, color=C["neg"], fontsize=9,
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#FCEBEB", edgecolor=C["neg"], lw=0.8))
            ax.set_title(f"{rd['label']}  ·  {rd['name']}  ·  {days}d held", fontsize=9, color=C["text"], loc="left", pad=5)
            continue

        ax.plot(dates, s_rb, color=C["stock"], lw=2, label=rd["label"], zorder=3)
        if n_rb:
            ax.plot(dates, n_rb, color=C["nifty"], lw=1.3, ls="--", label="Nifty 50", zorder=2)
            ax.fill_between(dates, s_rb, n_rb,
                where=[s >= nn for s,nn in zip(s_rb,n_rb)], alpha=0.09, color=C["stock"], zorder=1)
            ax.fill_between(dates, s_rb, n_rb,
                where=[s < nn for s,nn in zip(s_rb,n_rb)], alpha=0.09, color=C["sensex"], zorder=1)
        if x_rb:
            ax.plot(dates, x_rb, color=C["sensex"], lw=1.3, ls=":", label="Sensex", zorder=2)

        ax.axvline(buy_dt, color=C["buy"], lw=1.8, ls="--", zorder=4)
        ax.text(buy_dt, max(s_rb)*0.998, f"  Buy Rs.{rd['buy_low']}",
                fontsize=7.5, color=C["buy"], va="top", fontweight="bold", zorder=5)

        if rd.get("target"):
            tpct = rd["target"] / rd["buy_low"] * 100
            ax.axhline(tpct, color="#9B59B6", lw=1, ls=(0,(4,3)), alpha=0.75, zorder=2)
            ax.text(dates[-1], tpct+0.3, f"  Target {tpct:.0f}%", fontsize=7, color="#9B59B6", va="bottom", zorder=5)

        for ev in [e for e in news_events if e["symbol"] in (rd["label"], "ALL")]:
            ev_d = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if ev_d in dates:
                idx = dates.index(ev_d)
                col = IMPACT.get(ev["impact"], C["neu"])
                ax.scatter(ev_d, s_rb[idx], color=col, s=55, zorder=6, edgecolors="white", linewidths=0.9)
                ax.annotate(ev["text"][:36]+("…" if len(ev["text"])>36 else ""),
                    (ev_d, s_rb[idx]), xytext=(5,7), textcoords="offset points",
                    fontsize=6.2, color=col, rotation=18, zorder=7)

        s_p = pct(s_rb); n_p = pct(n_rb); x_p = pct(x_rb)
        al = round(s_p - n_p, 2) if n_rb else None
        for val, col in [(s_rb[-1], C["stock"]),
                         (n_rb[-1] if n_rb else None, C["nifty"]),
                         (x_rb[-1] if x_rb else None, C["sensex"])]:
            if val is not None:
                ax.text(1.005, val, f"{sign(val-100)}{val-100:.1f}%",
                        transform=ax.get_yaxis_transform(), fontsize=7.5, color=col, va="center", fontweight="bold")

        al_str = f"  |  Alpha vs Nifty: {sign(al)}{al}%" if al is not None else ""
        ax.set_title(f"{rd['label']}  ·  {rd['name']}  ·  {days}d held{al_str}",
                     fontsize=9, color=C["text"], loc="left", pad=5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        fig.autofmt_xdate(rotation=30, ha="right")
        leg = ax.legend(fontsize=7.5, loc="upper left", framealpha=0.85, edgecolor=C["grid"], handlelength=1.8)
        leg.get_frame().set_linewidth(0.5)

    plt.tight_layout(rect=[0, 0, 0.94, 0.99], h_pad=2.5)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    buf.seek(0)
    return buf


# ── Caption ───────────────────────────────────────────────────────────────────
def build_caption(recs_data, detail_url):
    today = datetime.now().strftime("%d %b %Y, %I:%M %p")
    lines = [f"*Portfolio Summary — {today} IST*\n"]
    for rd in recs_data:
        s_p = pct(rd["stock_rb"]); n_p = pct(rd["nifty_rb"]); x_p = pct(rd["sensex_rb"])
        al = round(s_p - n_p, 2)
        days = (date.today() - datetime.strptime(rd["buy_date"], "%Y-%m-%d").date()).days
        em = "🟢" if s_p >= 0 else "🔴"
        if not rd["stock_rb"]:
            lines.append(f"⚠️ *{rd['label']}* — rate limited, retry tomorrow\n"); continue
        lines.append(
            f"{em} *{rd['label']}* ({rd['type']} · {days}d)\n"
            f"   Stock `{sign(s_p)}{s_p}%`  Nifty `{sign(n_p)}{n_p}%`  Sensex `{sign(x_p)}{x_p}%`\n"
            f"   Alpha vs Nifty: `{sign(al)}{al}%`"
        )
        if rd.get("target"):
            up = round((rd["target"]/rd["buy_low"]-1)*100, 1)
            lines.append(f"   Target ₹{rd['target']}  ({sign(up)}{up}% upside)")
        lines.append("")
    lines.append(f"[📊 Full charts & news]({detail_url})")
    return "\n".join(lines)


# ── Core update job ───────────────────────────────────────────────────────────
async def run_update(bot: Bot):
    log.info("=== Daily update starting ===")
    recs = load_recs()
    news = load_news()
    now  = datetime.now().strftime("%d %b %Y %H:%M IST")

    earliest = min(r["buy_date"] for r in recs)

    # Fetch indices first, then pause before stocks
    log.info("Fetching index data...")
    nifty_dates,  nifty_closes  = fetch_prices("^NSEI",  earliest)
    await asyncio.sleep(30)  # wait 30s between index fetches
    sensex_dates, sensex_closes = fetch_prices("^BSESN", earliest)

    recs_data = []
    for i, rec in enumerate(recs):
        await asyncio.sleep(30)  # 30s gap between every symbol — key fix for rate limiting
        log.info(f"Fetching {rec['symbol']} ({i+1}/{len(recs)})...")
        s_dates, s_closes = fetch_prices(rec["symbol"], rec["buy_date"])

        common, s_al, n_al = align(s_dates, s_closes, nifty_dates, nifty_closes) if (s_dates and nifty_dates) else (s_dates, s_closes, [])
        _, _, x_al = align(s_dates, s_closes, sensex_dates, sensex_closes) if (s_dates and sensex_dates) else ([], [], [])

        recs_data.append(dict(
            label=rec["label"], name=rec["name"], buy_date=rec["buy_date"],
            buy_low=rec["buy_low"], buy_high=rec["buy_high"],
            type=rec["type"], target=rec.get("target"), symbol=rec["symbol"],
            dates=common if common else s_dates,
            stock_rb=rebase(s_al) if s_al else rebase(s_closes),
            nifty_rb=rebase(n_al), sensex_rb=rebase(x_al),
            stock_closes=s_al or s_closes, nifty_closes=n_al, sensex_closes=x_al,
        ))

    # Deploy to Netlify
    detail_url = None
    try:
        html = build_html(recs_data, news, now)
        detail_url = deploy(html)
    except Exception as e:
        log.error(f"Netlify deploy failed: {e}")
        detail_url = f"https://{NETLIFY_SITE_ID}"

    chart_buf = make_chart(recs_data, news)
    caption   = build_caption(recs_data, detail_url)

    await bot.send_photo(
        chat_id=CHAT_ID, photo=chart_buf,
        caption=caption, parse_mode=ParseMode.MARKDOWN,
    )
    log.info("=== Update sent ✓ ===")


# ── Telegram command handlers ─────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 *Investment Tracker Bot*\n\n"
        "Commands:\n"
        "/list — show all tracked stocks\n"
        "/add — add a new recommendation\n"
        "/remove SYMBOL — stop tracking a stock\n"
        "/news — add a news event\n"
        "/update — trigger an immediate update\n",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    recs = load_recs()
    if not recs:
        await update.message.reply_text("No stocks being tracked yet.")
        return
    lines = ["*Tracked recommendations:*\n"]
    for r in recs:
        days = (date.today() - datetime.strptime(r["buy_date"], "%Y-%m-%d").date()).days
        tgt = f"  Target ₹{r['target']}" if r.get("target") else ""
        lines.append(f"• *{r['label']}* — Buy ₹{r['buy_low']}–{r['buy_high']} on {r['buy_date']} ({days}d){tgt}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Usage:
      /add SYMBOL NAME BUY_DATE BUY_LOW BUY_HIGH TYPE [TARGET]

    Example:
      /add INFY.NS Infosys 2026-05-01 1820 1825 Positional
      /add TCS.NS TCS 2026-05-01 3950 3960 MediumTerm 5000
    """
    args = ctx.args
    if not args or len(args) < 6:
        await update.message.reply_text(
            "*Usage:*\n"
            "`/add SYMBOL NAME DATE BUY\\_LOW BUY\\_HIGH TYPE [TARGET]`\n\n"
            "*Example:*\n"
            "`/add INFY.NS Infosys 2026-05-01 1820 1825 Positional`\n"
            "`/add TCS.NS TCS 2026-05-02 3950 3960 MediumTerm 5000`\n\n"
            "SYMBOL must end in `.NS` for NSE stocks\\.\n"
            "TYPE: `Positional` or `MediumTerm`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    symbol   = args[0].upper()
    name     = args[1]
    buy_date = args[2]
    try:
        buy_low  = float(args[3])
        buy_high = float(args[4])
        rec_type = args[5]
        target   = float(args[6]) if len(args) > 6 else None
    except ValueError:
        await update.message.reply_text("❌ BUY_LOW, BUY_HIGH and TARGET must be numbers.")
        return

    # Validate date
    try:
        datetime.strptime(buy_date, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ DATE must be in YYYY-MM-DD format, e.g. 2026-05-01")
        return

    # Derive label from symbol (strip .NS)
    label = symbol.replace(".NS", "").replace(".BO", "")

    recs = load_recs()
    # Check duplicate
    if any(r["label"] == label for r in recs):
        await update.message.reply_text(f"⚠️ {label} is already being tracked. Use /remove {label} first if you want to re-add it.")
        return

    recs.append({
        "symbol":   symbol,
        "label":    label,
        "name":     name,
        "buy_date": buy_date,
        "buy_low":  buy_low,
        "buy_high": buy_high,
        "target":   target,
        "type":     rec_type,
    })
    save_recs(recs)

    tgt_str = f"  Target: ₹{target}" if target else ""
    await update.message.reply_text(
        f"✅ *{label}* added\n"
        f"Buy ₹{buy_low}–{buy_high} on {buy_date}{tgt_str}\n"
        f"Will appear in tomorrow's update. Use /update to refresh now.",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /remove SYMBOL  e.g. /remove INFY")
        return
    label = ctx.args[0].upper().replace(".NS","").replace(".BO","")
    recs = load_recs()
    before = len(recs)
    recs = [r for r in recs if r["label"] != label]
    if len(recs) == before:
        await update.message.reply_text(f"❌ {label} not found. Use /list to see tracked stocks.")
        return
    save_recs(recs)
    await update.message.reply_text(f"🗑 *{label}* removed from tracking.", parse_mode=ParseMode.MARKDOWN)

async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /news SYMBOL DATE impact TEXT
    Example:
      /news INFY 2026-05-03 pos Q4 results beat estimates
      /news ALL 2026-05-05 neu RBI policy unchanged
    impact: pos | neu | neg
    """
    if not ctx.args or len(ctx.args) < 4:
        await update.message.reply_text(
            "*Usage:* `/news SYMBOL DATE impact Text of news`\n\n"
            "*Examples:*\n"
            "`/news INFY 2026-05-03 pos Q4 results beat estimates`\n"
            "`/news ALL 2026-05-05 neu RBI policy unchanged`\n\n"
            "Use `ALL` as SYMBOL to show on every chart\\.\n"
            "impact: `pos` \\| `neu` \\| `neg`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    symbol = ctx.args[0].upper()
    date_s = ctx.args[1]
    impact = ctx.args[2].lower()
    text   = " ".join(ctx.args[3:])

    try:
        datetime.strptime(date_s, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ DATE must be YYYY-MM-DD")
        return
    if impact not in ("pos", "neu", "neg"):
        await update.message.reply_text("❌ impact must be: pos | neu | neg")
        return

    news = load_news()
    news.append({"date": date_s, "symbol": symbol, "text": text, "impact": impact})
    save_news(news)
    await update.message.reply_text(
        f"📰 News event added for *{symbol}* on {date_s}\n_{text}_",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Running update now — this takes a few minutes due to rate limiting delays...")
    bot = ctx.bot
    try:
        await run_update(bot)
    except Exception as e:
        await update.message.reply_text(f"❌ Update failed: {e}")


# ── Scheduler job wrapper ─────────────────────────────────────────────────────
async def scheduled_update(bot: Bot):
    try:
        await run_update(bot)
    except Exception as e:
        log.error(f"Scheduled update failed: {e}")
        await bot.send_message(chat_id=CHAT_ID, text=f"⚠️ Daily update failed: {e}")


# ── Entrypoint ────────────────────────────────────────────────────────────────
async def main():
    log.info(f"Bot starting — daily at {SEND_HOUR}:00 {TIMEZONE}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CommandHandler("add",    cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("news",   cmd_news))
    app.add_handler(CommandHandler("update", cmd_update))

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        scheduled_update, "cron",
        hour=SEND_HOUR, minute=0,
        args=[app.bot]
    )
    scheduler.start()

    # Send once on startup
    await run_update(app.bot)

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
