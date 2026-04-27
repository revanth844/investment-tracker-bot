# Fix: "No data available" on all charts

## Root causes (all 3 were present)

### 1. Missing User-Agent header — Yahoo blocks bot IPs
Yahoo Finance rejects requests from cloud server IPs (Railway, AWS, GCP)
that don't send a browser User-Agent. Without it, yfinance returns an empty
DataFrame silently — no exception, no error, just no rows.

**Fix applied:** A `requests.Session` with a Chrome User-Agent is passed
into every `yf.Ticker()` call.

```python
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..."
})
tk = yf.Ticker(symbol, session=session)
```

---

### 2. No retries — single transient timeout = permanent blank chart
Railway free tier IPs are sometimes slow on first connection to Yahoo.
One timeout meant zero data for the whole day.

**Fix applied:** 3 attempts with exponential backoff (2s, 4s, 8s + jitter).

---

### 3. Date alignment — stock, Nifty, Sensex trade on slightly different
holiday calendars, causing `fill_between` and the label overlay to crash
silently when array lengths mismatched.

**Fix applied:** `align()` function finds common trading dates across all
three series before rebasing. Partial data (e.g. Nifty fetched but Sensex
failed) renders what's available rather than showing nothing.

---

## How to redeploy

```bash
# In your investment-bot folder:
git add bot.py requirements.txt
git commit -m "fix: user-agent, retries, date alignment"
git push
```

Railway auto-redeploys on push. Watch the Logs tab for:
```
[TITAN.NS] fetched 45 days from 2026-03-13 to 2026-04-26
[^NSEI] fetched 45 days from 2026-03-13 to 2026-04-26
Message sent ✓
```

If you still see empty data, check logs for the exact symbol failing and
verify it on https://finance.yahoo.com/quote/TITAN.NS

---

## Railway-specific: prevent sleep on free tier

Railway free tier pauses workers after inactivity. Add a no-op HTTP
health-check endpoint so UptimeRobot can ping it every 5 min:

Add to bot.py (optional):
```python
from aiohttp import web
async def health(request):
    return web.Response(text="ok")

async def run_server():
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()
```
Then add `pip install aiohttp` to requirements.txt and set a free monitor
at https://uptimerobot.com pointing to your Railway app URL + /health.
