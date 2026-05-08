# 📈 Investment Advisor Tracker Bot — Setup Guide

Daily Telegram bot that tracks equity recommendations, sends a chart + performance
summary rebased from buy date vs Nifty 50 & Sensex, and suggests hedging strategies
when a new position is added.

---

## What you'll get every morning

A Telegram message with:

- **One image** — one chart per tracked stock, each showing:
  - Stock line vs Nifty 50 (dashed green) vs Sensex (dotted orange)
  - Buy-date vertical line with entry price
  - News event dots annotated on the chart
  - Shaded alpha region (blue = outperforming, red = underperforming Nifty)
  - % return labels on the right edge
- **Caption** — emoji summary per stock with source, alpha vs Nifty, and target
- **Link** to your interactive web app (hosted on Netlify)

---

## Files in this project

```
investment-bot/
├── bot.py                  ← main bot (scheduler + chart + Telegram commands)
├── price_fetcher.py        ← 3-source price waterfall: NSE Bhavcopy → openchart → yfinance
├── netlify_deploy.py       ← builds interactive HTML and deploys to Netlify
├── hedge_analyzer.py       ← Claude API: auto-generates hedging suggestions on /add
├── gmail_parser.py         ← auto-imports Axis Direct email recommendations (optional)
├── dryrun.py               ← offline test, no API keys needed
├── requirements.txt
├── Procfile                ← Railway process definition
├── railway.toml            ← Railway config
├── data/
│   ├── recommendations.json   ← auto-created on first run
│   └── news_events.json       ← auto-created on first run
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

## STEP 2 — Set up Netlify (interactive web app)

The bot deploys a live interactive chart page to Netlify after every update.

1. Go to [netlify.com](https://netlify.com) → sign up / log in
2. Go to **User Settings → Applications → Personal access tokens** → create a token
   → save as `NETLIFY_TOKEN`
3. Create a new **blank site** (Sites → Add new site → Deploy manually → drag any file)
   → copy the **Site ID** from Site Settings → save as `NETLIFY_SITE_ID`

---

## STEP 3 — Get an Anthropic API key (hedge analysis)

The bot uses Claude to generate hedging suggestions whenever a new recommendation
is added via `/add` or auto-imported from email.

1. Go to [console.anthropic.com](https://console.anthropic.com) → API Keys → Create key
2. Save as `ANTHROPIC_API_KEY`

> If this key is not set, hedge analysis is silently skipped — everything else works normally.

---

## STEP 4 — Push code to GitHub (3 min)

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

## STEP 5 — Deploy on Railway (5 min)

1. Go to [railway.app](https://railway.app) → **Login with GitHub**
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `investment-bot` repo
4. Railway will detect Python and start building

### Set environment variables (Railway Dashboard → your project → Variables)

| Variable               | Value                                                              |
| ---------------------- | ------------------------------------------------------------------ |
| `TELEGRAM_TOKEN`       | `7412356789:AAFxyz_abc...` (from Step 1) — **required**           |
| `CHAT_ID`              | `123456789` (from Step 1) — **required**                          |
| `NETLIFY_TOKEN`        | Personal access token (from Step 2) — **required**                |
| `NETLIFY_SITE_ID`      | Site ID from Netlify (from Step 2) — **required**                 |
| `ANTHROPIC_API_KEY`    | `sk-ant-...` (from Step 3) — optional, enables hedge analysis     |
| `SEND_HOUR`            | `15` — optional, default `15` (3 PM IST, after market close)      |
| `GMAIL_CLIENT_ID`      | OAuth2 credential — see `GMAIL_SETUP.md` (optional)               |
| `GMAIL_CLIENT_SECRET`  | OAuth2 credential — see `GMAIL_SETUP.md` (optional)               |
| `GMAIL_REFRESH_TOKEN`  | OAuth2 credential — see `GMAIL_SETUP.md` (optional)               |

5. Click **Deploy** — Railway will install requirements and start the bot
6. Check the **Logs** tab — you should see the bot send an update on startup
7. Check your Telegram — the bot sends once immediately ✅

---

## STEP 6 — Add recommendations via Telegram

Just message your bot directly — no code editing needed:

```
/add INFY.NS Infosys 2026-05-01 1820 1825 Positional
/add TCS.NS TCS 2026-05-02 3950 3960 MediumTerm 5000 Axis Direct
/add SBIN.NS "State Bank" 2026-05-03 830 832 Positional - Self Research
```

**Syntax:** `/add SYMBOL NAME DATE BUY_LOW BUY_HIGH TYPE [TARGET] [SOURCE]`

- `SYMBOL` — NSE ticker with `.NS` suffix (e.g. `RELIANCE.NS`, `TCS.NS`)
- `TARGET` — optional target price; use `-` to skip it and still set a source
- `SOURCE` — optional, multi-word (e.g. `Axis Direct`, `Self Research`)

After saving, the bot automatically fetches the current price and sends a
hedging analysis from Claude as a follow-up message.

---

## Recommendation data format

`data/recommendations.json` is created automatically. Each entry looks like:

```json
{
  "symbol":   "INFY.NS",
  "label":    "INFY",
  "name":     "Infosys",
  "buy_date": "2026-05-01",
  "buy_low":  1820.0,
  "buy_high": 1825.0,
  "target":   2200.0,
  "type":     "Medium Term",
  "source":   "Axis Direct"
}
```

`source` is optional — cards and captions show it when present.

---

## Add news events

```
/news INFY 2026-05-03 pos Q4 results beat estimates
/news ALL 2026-05-05 neu RBI policy: rates held
```

**Syntax:** `/news SYMBOL DATE impact Text`

- `SYMBOL` — stock label, or `ALL` to show on every chart
- `impact` — `pos` (green dot), `neu` (grey dot), `neg` (red dot)

---

## Hedge analysis

Hedge suggestions are sent automatically in two situations:

1. **On `/add`** — immediately after a new recommendation is saved
2. **On Gmail auto-import** — for each newly imported recommendation

You can also request analysis on-demand at any time:

```
/hedge TITAN
/hedge RELIANCE
```

The bot fetches the current price and asks Claude for 2–3 concrete NSE options
strategies with specific strikes, expiries, and approximate premiums.

---

## Dry run (offline test, no Telegram needed)

```bash
python dryrun.py
```

Generates `output.html` and prints the full Telegram caption to your terminal.
Use this to verify any new stock or news before deploying.

---

## Schedule customisation

Change `SEND_HOUR` env variable to any hour (IST, 24h format):

- `8` → 8:00 AM IST
- `15` → 3:00 PM IST (after market close — **recommended**)
- `18` → 6:00 PM IST

> Recommended: `15` or `16` — NSE Bhavcopy is published around 6 PM IST,
> so intraday prices come from openchart; EOD prices appear the next morning.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Chart is blank / no data | Check Railway logs for price fetch errors; NSE data can lag 1 day |
| `CHAT_ID` error | Send at least one message to the bot before checking getUpdates |
| Railway build fails | Check `requirements.txt`; Railway uses Python 3.11 by default |
| Stock not found | Verify `.NS` suffix; check on [finance.yahoo.com](https://finance.yahoo.com) |
| Netlify deploy fails | Verify `NETLIFY_TOKEN` and `NETLIFY_SITE_ID` are set correctly |
| No hedge analysis | Confirm `ANTHROPIC_API_KEY` is set in Railway variables |
| Bot stopped sending | Railway free tier sleeps — upgrade to Hobby ($5/mo) or add a UptimeRobot ping |

---

## Cost

| Service | Cost |
|---------|------|
| Telegram Bot API | Free |
| Railway (Starter) | Free — 500 hrs/month (enough for 1 worker) |
| Netlify (Starter) | Free — 100 GB bandwidth/month |
| NSE Bhavcopy / openchart | Free, no API key |
| Yahoo Finance (yfinance) | Free, no API key |
| Anthropic API (hedge analysis) | ~$0.01–0.05/month at Haiku rates (optional) |
| **Total** | **~₹0–4 / month** |

---

## Full command reference

| Command | What it does |
|---------|--------------|
| `/list` | Show all tracked stocks with source and target |
| `/add SYMBOL NAME DATE LOW HIGH TYPE [TARGET] [SOURCE]` | Add a recommendation; triggers hedge analysis |
| `/remove SYMBOL` | Stop tracking a stock |
| `/hedge SYMBOL` | Get on-demand hedging suggestions for a tracked stock |
| `/news SYMBOL DATE pos/neu/neg Text` | Add a news event to the chart |
| `/update` | Trigger an immediate chart update and Netlify deploy |

---

*See also: `GMAIL_SETUP.md` for auto-importing Axis Direct email recommendations.*
