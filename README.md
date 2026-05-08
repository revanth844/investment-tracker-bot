# Investment Advisor Tracker Bot

Daily Telegram bot that tracks NSE equity recommendations, charts performance
vs Nifty 50 & Sensex from buy date, and suggests hedging strategies when a
new position is added.

---

## What it does

- Sends a **daily chart image** at a configurable time — one subplot per tracked stock,
  rebased from buy date with buy-date marker, alpha shading vs Nifty, and news event dots
- Deploys a **live interactive web page** to Netlify after every update
- **Auto-suggests hedges** via Claude API whenever a new recommendation is added
- Accepts all commands via **Telegram** — no code editing needed after setup
- Price data uses a 3-source waterfall: NSE Bhavcopy → openchart → Yahoo Finance

---

## Docs

| Document | What it covers |
| --- | --- |
| [Setup guide](docs/SETUP.md) | End-to-end setup: Telegram, Netlify, Railway, all env vars |
| [Netlify credentials](docs/GET_NETLIFY_CREDENTIALS.md) | How to get `NETLIFY_TOKEN` and `NETLIFY_SITE_ID` |
| [Gmail OAuth setup](docs/GMAIL_SETUP.md) | How to get Gmail credentials for Axis Direct email auto-import |
| [Fix: no data on charts](docs/FIX_NO_DATA.md) | Troubleshooting blank charts (User-Agent, retries, date alignment) |

---

## Commands

| Command | What it does |
| --- | --- |
| `/list` | Show all tracked stocks with source and target |
| `/add SYMBOL NAME DATE LOW HIGH TYPE [TARGET] [SOURCE]` | Add a recommendation; triggers hedge analysis |
| `/remove SYMBOL` | Stop tracking a stock |
| `/hedge SYMBOL` | Get on-demand hedging suggestions for a tracked stock |
| `/news SYMBOL DATE pos/neu/neg Text` | Add a news event to the chart |
| `/update` | Trigger an immediate chart update and Netlify deploy |

**Add examples:**

```bash
/add INFY.NS Infosys 2026-05-01 1820 1825 Positional
/add TCS.NS TCS 2026-05-02 3950 3960 MediumTerm 5000 Axis Direct
/add SBIN.NS "State Bank" 2026-05-03 830 832 Positional - Self Research
```

---

## Project structure

```text
├── src/
│   ├── bot.py                     ← scheduler, chart generation, Telegram commands
│   ├── price_fetcher.py           ← 3-source price waterfall
│   ├── netlify_deploy.py          ← interactive HTML builder + Netlify deploy
│   ├── hedge_analyzer.py          ← Claude API hedge suggestions
│   ├── gmail_parser.py            ← Axis Direct email auto-import
│   ├── dryrun.py                  ← offline test (no API keys needed)
│   ├── get_gmail_refresh_token.py ← one-time OAuth token helper
│   └── test_deploy.py             ← Netlify deploy smoke test
├── docs/                          ← setup and reference documentation
├── data/                          ← recommendations.json, news_events.json (auto-created)
├── charts/                        ← chart images (auto-created)
├── Procfile
└── railway.toml
```

---

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_TOKEN` | Yes | Bot token from @BotFather |
| `CHAT_ID` | Yes | Your Telegram chat/group ID |
| `NETLIFY_TOKEN` | Yes | Netlify personal access token |
| `NETLIFY_SITE_ID` | Yes | Netlify site ID or subdomain |
| `ANTHROPIC_API_KEY` | Optional | Enables Claude hedge analysis |
| `SEND_HOUR` | Optional | Hour to send daily update (IST, default `15`) |
| `GMAIL_CLIENT_ID` | Optional | Enables Axis Direct email auto-import |
| `GMAIL_CLIENT_SECRET` | Optional | Gmail OAuth credential |
| `GMAIL_REFRESH_TOKEN` | Optional | Gmail OAuth credential |

See [docs/SETUP.md](docs/SETUP.md) for step-by-step instructions.

---

## Dry run (no API keys needed)

```bash
pip install -r requirements.txt
python src/dryrun.py
```

Generates `charts/dryrun_summary.png` with simulated prices and prints the
Telegram caption preview to your terminal.
