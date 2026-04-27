# Gmail OAuth Setup — Get GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN

The bot needs read-only Gmail access to pull Axis Direct research emails.
Takes ~15 minutes. Everything is done in Google Cloud — free.

---

## Step 1 — Create a Google Cloud project

1. Go to https://console.cloud.google.com
2. Click the project dropdown (top left) → **New Project**
3. Name it: `investment-bot` → **Create**
4. Make sure the new project is selected

---

## Step 2 — Enable Gmail API

1. Go to **APIs & Services → Library**
2. Search for **Gmail API** → click it → **Enable**

---

## Step 3 — Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. If prompted to configure consent screen:
   - User type: **External** → Create
   - App name: `investment-bot`
   - User support email: your Gmail
   - Developer contact: your Gmail
   - Click **Save and Continue** through all steps
   - On Scopes page: click **Add or Remove Scopes**
     → search `gmail.readonly` → tick it → Update → Save
   - On Test Users page: **+ Add Users** → add your Gmail → Save
4. Back on Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: `investment-bot`
   - Click **Create**
5. Copy and save:
   - **Client ID** → this is `GMAIL_CLIENT_ID`
   - **Client Secret** → this is `GMAIL_CLIENT_SECRET`

---

## Step 4 — Get your Refresh Token (one-time, run locally)

Run this Python script on your computer (not Railway):

```python
# get_token.py — run once locally to get your refresh token
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID     = "YOUR_CLIENT_ID_HERE"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
        }
    },
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
)

creds = flow.run_local_server(port=0)
print(f"\nGMAIL_REFRESH_TOKEN = {creds.refresh_token}")
```

Install dependency first:
```bash
pip install google-auth-oauthlib
python get_token.py
```

A browser window opens → sign in with your Gmail → Allow → copy the printed token.

---

## Step 5 — Add to Railway environment variables

| Variable              | Value                          |
|-----------------------|--------------------------------|
| `GMAIL_CLIENT_ID`     | `xxxx.apps.googleusercontent.com` |
| `GMAIL_CLIENT_SECRET` | `GOCSPX-xxxx`                  |
| `GMAIL_REFRESH_TOKEN` | `1//xxxx`                      |

**Never paste these in chat.** Add directly in Railway → Variables.

---

## How it works

Every morning before the chart update:
1. Bot searches Gmail for emails from `services@axisdirect.in` in the last 7 days
2. Parses subject/body for: company name, CMP, target, stop loss, duration
3. Looks up the NSE ticker symbol via Yahoo Finance search
4. Adds new recommendations to `recommendations.json` (skips duplicates)
5. Sends a Telegram notification listing what was auto-imported
6. Those stocks appear in the same day's chart update

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing OAuth credentials` in logs | Check all 3 env vars are set in Railway |
| `Token refresh failed 401` | Refresh token expired — re-run get_token.py |
| `Could not parse company name` | Email format changed — check Railway logs, use `/add` manually |
| `Could not resolve NSE symbol` | Yahoo search returned nothing — use `/add SYMBOL.NS Name Date...` |
| Bot adds wrong symbol | Use `/remove WRONGSYMBOL` then `/add CORRECT.NS Name Date...` |
