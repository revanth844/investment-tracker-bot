# 📈 Investment Advisor Tracker Bot — Setup Guide

Daily Telegram bot that sends a chart + performance summary for all tracked
recommendations, rebased from buy date vs Nifty 50 & Sensex.

---

## What you'll get every morning

A Telegram message with:
- **One image** — 4 stacked charts (one per stock), each showing:
  - Stock line vs Nifty 50 (dashed green) vs Sensex (dotted orange)
  - Buy-date vertical line with entry price
  - News event dots annotated on the chart
  - Shaded alpha region (blue = outperforming, red = underperforming Nifty)
  - % return labels on the right edge
- **Caption** — emoji summary per stock with Alpha vs Nifty
- **Link** to your detailed interactive web app

---

## Files in this project

```
investment-bot/
├── bot.py                  ← main bot (scheduler + chart + Telegram sender)
├── dryrun.py               ← offline test, no API keys needed
├── requirements.txt
├── Procfile                ← Railway process definition
├── railway.toml            ← Railway config
├── data/
│   └── recommendations.json  ← auto-created on first run
└── charts/                 ← temp chart images (auto-created)
```

---

## STEP 1 — Create your Telegram Bot (5 min)

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Choose a name: e.g. `My Portfolio Tracker`
4. Choose a username: e.g. `myportfolio_tracker_bot`
5. BotFather replies with a **token** like:
   ```
   7412356789:AAFxyz_abcdefghijklmnopqrstuvwxyz123
   ```
   → Save this as `TELEGRAM_TOKEN`

6. **Get your Chat ID:**
   - Start a chat with your new bot (click the link BotFather gives you → Start)
   - Open this URL in your browser (replace TOKEN):
     ```
     https://api.telegram.org/bot<TOKEN>/getUpdates
     ```
   - Send any message to your bot, refresh the URL
   - Look for `"chat":{"id":123456789}` — that number is your `CHAT_ID`

> **Tip:** To send to a group, add the bot to the group, send a message,
> and the group's chat ID will appear in getUpdates (it starts with `-`).

---

## STEP 2 — Push code to GitHub (3 min)

1. Go to [github.com/new](https://github.com/new)
2. Create a **private** repo called `investment-bot`
3. On your computer, run:

```bash
cd investment-bot
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_USERNAME/investment-bot.git
git push -u origin main
```

---

## STEP 3 — Deploy on Railway (5 min)

1. Go to [railway.app](https://railway.app) → **Login with GitHub**
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `investment-bot` repo
4. Railway will detect Python and start building

### Set environment variables (Railway Dashboard → your project → Variables):

| Variable         | Value                                      |
|------------------|--------------------------------------------|
| `TELEGRAM_TOKEN` | `7412356789:AAFxyz_abc...` (from Step 1)   |
| `CHAT_ID`        | `123456789` (from Step 1)                  |
| `SEND_HOUR`      | `8` (sends at 8:00 AM IST daily)           |
| `DETAIL_URL`     | `https://your-detail-app.netlify.app`      |

5. Click **Deploy** — Railway will install requirements and start the bot
6. Check **Logs** tab — you should see:
   ```
   Bot starting — will send at 8:00 Asia/Kolkata daily
   Running daily update job…
   Chart saved → charts/daily_summary.png
   Message sent ✓
   ```
7. Check your Telegram — the bot sends once immediately on startup ✅

---

## STEP 4 — Add new recommendations

Edit `data/recommendations.json` directly on Railway (or push a new commit):

```json
[
  {
    "symbol":   "TITAN.NS",
    "label":    "TITAN",
    "name":     "Titan Company",
    "buy_date": "2026-03-13",
    "buy_low":  4133.0,
    "buy_high": 4134.0,
    "target":   null,
    "type":     "Positional"
  },
  {
    "symbol":   "INFY.NS",
    "label":    "INFY",
    "name":     "Infosys",
    "buy_date": "2026-05-01",
    "buy_low":  1820.0,
    "buy_high": 1825.0,
    "target":   2200.0,
    "type":     "Medium Term"
  }
]
```

**NSE symbol format:** Always append `.NS` for NSE stocks (e.g. `RELIANCE.NS`, `TCS.NS`)
**Indices used internally:** `^NSEI` (Nifty 50), `^BSESN` (Sensex) — no suffix needed.

---

## STEP 5 — Add news events

Edit the `NEWS_EVENTS` list in `bot.py`:

```python
NEWS_EVENTS = [
    # symbol = stock label OR "ALL" (shows on every chart)
    {"date": "2026-05-02", "symbol": "INFY",  "text": "Q4 results beat estimates", "impact": "pos"},
    {"date": "2026-05-05", "symbol": "ALL",   "text": "RBI policy: rates held",    "impact": "neu"},
]
```

`impact` values: `"pos"` (green dot), `"neu"` (grey dot), `"neg"` (red dot)

---

## Dry run (offline test, no Telegram needed)

```bash
python dryrun.py
```

Generates `charts/dryrun_summary.png` and prints the full Telegram caption
to your terminal. Use this to verify any new stock or news before deploying.

---

## Schedule customisation

Change `SEND_HOUR` env variable to any hour (IST, 24h format):
- `8` → 8:00 AM IST
- `15` → 3:00 PM IST (after market close — recommended for accurate data)
- `18` → 6:00 PM IST

> **Recommended:** Set to `15` or `16` so yfinance has the day's closing
> prices before the message is sent.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Bot sends but chart is blank | Check Railway logs for yfinance errors; NSE data can lag by 1 day |
| `CHAT_ID` error | Make sure you sent at least one message to the bot before checking getUpdates |
| Railway build fails | Check `requirements.txt` versions; Railway uses Python 3.11 by default |
| Stock not found | Verify the `.NS` suffix; check on [finance.yahoo.com](https://finance.yahoo.com) |
| Bot stopped sending | Railway free tier sleeps after inactivity — upgrade to Hobby ($5/mo) or add a ping service like UptimeRobot |

---

## Cost

| Service | Cost |
|---|---|
| Telegram Bot API | Free, unlimited |
| Railway (Starter) | Free — 500 hrs/month (enough for 1 worker) |
| Yahoo Finance (yfinance) | Free, no API key |
| **Total** | **₹0 / month** |

---

*Generated by Claude · Anthropic*
