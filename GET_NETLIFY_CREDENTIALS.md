# Getting NETLIFY_TOKEN and NETLIFY_SITE_ID

These two values are the only new things you need to add to Railway.
Takes about 8 minutes total.

---

## Step 1 — Create a free Netlify account

1. Go to https://app.netlify.com/signup
2. Sign up with email (no credit card needed)
3. Verify your email

---

## Step 2 — Create a blank site (gets you a permanent URL)

1. Log in to Netlify
2. Click **"Add new site"** → **"Deploy manually"**
3. Drag any file (even a blank .txt file) onto the upload area
4. Netlify creates your site with a URL like:
   `https://jade-croissant-4f3a1b.netlify.app`
   → **This URL never changes** — it's your permanent DETAIL_URL

5. Optionally rename it: Site settings → General → Change site name
   e.g. `myportfolio-tracker` → `https://myportfolio-tracker.netlify.app`

---

## Step 3 — Get your NETLIFY_SITE_ID

**Option A (easier):** From the URL itself
- If your site is `https://jade-croissant-4f3a1b.netlify.app`
- Your NETLIFY_SITE_ID = `jade-croissant-4f3a1b.netlify.app`

**Option B:** From the dashboard
1. Go to your site in Netlify dashboard
2. Click **Site configuration** → **General**
3. Copy the **Site ID** (looks like `a1b2c3d4-e5f6-...`)
   Either the UUID or the subdomain name both work.

---

## Step 4 — Get your NETLIFY_TOKEN (Personal Access Token)

1. Click your **avatar** (top right) → **User settings**
2. Go to **Applications** tab
3. Under "Personal access tokens" → click **"New access token"**
4. Name it: `investment-bot`
5. Expiration: **No expiration** (so the bot keeps working)
6. Click **Generate token**
7. **Copy it immediately** — Netlify only shows it once
   Looks like: `nfp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

---

## Step 5 — Add to Railway environment variables

In Railway → your project → Variables, add:

| Variable          | Value                                          |
|-------------------|------------------------------------------------|
| `NETLIFY_TOKEN`   | `nfp_xxxx...` (from Step 4)                    |
| `NETLIFY_SITE_ID` | `jade-croissant-4f3a1b.netlify.app` (Step 3)  |

Then push the updated code:
```bash
git add bot.py netlify_deploy.py requirements.txt
git commit -m "feat: netlify auto-deploy"
git push
```

Railway redeploys automatically. On startup you'll see in logs:
```
Deploying to Netlify site jade-croissant-4f3a1b.netlify.app…
Deployed → https://jade-croissant-4f3a1b.netlify.app
Telegram message sent ✓
```

And your Telegram message will contain:
```
📊 Full charts & news → https://jade-croissant-4f3a1b.netlify.app
```

---

## How it works

Every morning at 15:00 IST:
1. Bot fetches live prices from Yahoo Finance
2. Generates a fresh `index.html` with all charts and news
3. Deploys it to the SAME Netlify URL (overwrites previous version)
4. Sends Telegram image + caption with the permanent link

The URL never changes — you can save it in WhatsApp once and it always
shows today's data when you open it.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `401 Unauthorized` from Netlify | Token expired or wrong — regenerate in Netlify → User Settings → Applications |
| `404 Not Found` from Netlify | NETLIFY_SITE_ID is wrong — use the full subdomain e.g. `abc.netlify.app` |
| HTML deploys but shows old data | Railway didn't restart — check logs, trigger manual redeploy |
| Netlify deploy succeeds but URL shows blank page | The HTML was empty — check `build_html()` returned content |
