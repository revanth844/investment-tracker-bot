"""
Standalone deploy test — no bot.py needed.
Run: NETLIFY_TOKEN=nfp_xxx python3 test_deploy.py
"""
import os, io, zipfile, json
import urllib.request, urllib.error

NETLIFY_TOKEN   = os.environ.get("NETLIFY_TOKEN", "")
NETLIFY_SITE_ID = "stalwart-meerkat-f33fb0.netlify.app"

HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Portfolio Tracker — Test Deploy</title>
<style>body{font-family:sans-serif;max-width:500px;margin:80px auto;text-align:center;color:#2c2c2a}
.ok{color:#3B6D11;font-size:48px;margin-bottom:16px}.title{font-size:22px;font-weight:500;margin-bottom:8px}
.sub{color:#888;font-size:14px}</style></head>
<body>
<div class="ok">&#10003;</div>
<div class="title">Deploy test successful</div>
<div class="sub">stalwart-meerkat-f33fb0.netlify.app is connected.<br>
The bot will replace this page with live charts every morning.</div>
</body></html>"""

def deploy_test():
    if not NETLIFY_TOKEN:
        print("ERROR: set NETLIFY_TOKEN env var first")
        print("  export NETLIFY_TOKEN=nfp_your_token_here")
        return

    # Build zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", HTML)
    buf.seek(0)
    zip_bytes = buf.read()

    url = f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys"
    req = urllib.request.Request(
        url,
        data=zip_bytes,
        headers={
            "Authorization": f"Bearer {NETLIFY_TOKEN}",
            "Content-Type":  "application/zip",
        },
        method="POST"
    )

    print(f"Deploying to: {NETLIFY_SITE_ID}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            site_url = data.get("ssl_url") or data.get("url", "")
            deploy_id = data.get("id", "")
            print(f"\n✅ SUCCESS")
            print(f"   Deploy ID : {deploy_id}")
            print(f"   Live URL  : {site_url}")
            print(f"\nOpen this in your browser to confirm:")
            print(f"   {site_url}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\n❌ HTTP {e.code}: {e.reason}")
        print(f"   {body[:300]}")
        if e.code == 401:
            print("\n→ Token is wrong or expired. Regenerate at:")
            print("  https://app.netlify.com/user/applications#personal-access-tokens")
        elif e.code == 404:
            print("\n→ Site ID not found. Double-check NETLIFY_SITE_ID.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

deploy_test()
