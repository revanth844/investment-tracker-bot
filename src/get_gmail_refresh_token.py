# get_token.py — run once locally to get your refresh token
import os

from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError(
        "Missing env vars: set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET before running."
    )

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