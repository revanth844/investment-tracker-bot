"""
gmail_parser.py
Pulls research recommendation emails from Services@axisdirect.in via Gmail API,
parses symbol / CMP / target / stop-loss / duration, and adds new ones to
recommendations.json — skipping any already tracked.

Called once daily before the main chart update runs.

Requires:
  GMAIL_CLIENT_ID     )  OAuth2 credentials — set in Railway env vars
  GMAIL_CLIENT_SECRET )  (see setup instructions below)
  GMAIL_REFRESH_TOKEN )
"""

import os, re, json, base64, logging
from datetime import datetime, date, timedelta
from pathlib import Path
import requests

log = logging.getLogger(__name__)

# ── Gmail OAuth2 ──────────────────────────────────────────────────────────────
GMAIL_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE     = "https://gmail.googleapis.com/gmail/v1/users/me"
AXIS_SENDER        = "services@axisdirect.in"

def _get_access_token() -> str | None:
    """Exchange refresh token for short-lived access token."""
    client_id     = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        log.warning("[gmail] Missing OAuth credentials — set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN")
        return None

    resp = requests.post(GMAIL_TOKEN_URL, data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }, timeout=10)

    if resp.status_code != 200:
        log.error(f"[gmail] Token refresh failed: {resp.text[:200]}")
        return None

    return resp.json().get("access_token")


def _gmail_get(path: str, token: str, params: dict = None) -> dict | None:
    """GET from Gmail API."""
    resp = requests.get(
        f"{GMAIL_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=15,
    )
    if resp.status_code != 200:
        log.error(f"[gmail] GET {path} failed {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


def _decode_body(msg: dict) -> str:
    """Extract plain-text or HTML body from Gmail message payload."""
    payload = msg.get("payload", {})

    def _extract(part):
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        if mime == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                raw = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                # Strip HTML tags for plain text parsing
                return re.sub(r"<[^>]+>", " ", raw)
        for sub in part.get("parts", []):
            result = _extract(sub)
            if result:
                return result
        return ""

    return _extract(payload)


# ── Axis Direct email parser ──────────────────────────────────────────────────
# Example body structure (from your sample):
#   Duration: 30 Days    Steel Authority of India Limited
#   CMP  Target  182  200   Upside  Stop Loss  10%  173

def _parse_axis_email(body: str, received_date: date) -> dict | None:
    """
    Parse an Axis Direct research email body into a recommendation dict.
    Returns None if parsing fails.
    """
    body = re.sub(r"\s+", " ", body).strip()  # collapse whitespace

    # ── Duration ──────────────────────────────────────────────────────────────
    dur_match = re.search(r"Duration[:\s]+(\d+)\s*Days?", body, re.IGNORECASE)
    duration_days = int(dur_match.group(1)) if dur_match else 30
    rec_type = "Short Term" if duration_days <= 15 else "Medium Term" if duration_days <= 60 else "Long Term"

    # ── Company name (between Duration line and CMP) ───────────────────────
    # Pattern: "Duration: 30 Days  <Company Name>  CMP..."
    name_match = re.search(
        r"Duration[:\s]+\d+\s*Days?\s+(.+?)\s+(?:CMP|Current\s*Market\s*Price)",
        body, re.IGNORECASE
    )
    if not name_match:
        # Fallback: try to find company name before price block
        name_match = re.search(r"Research\s+Idea\s+(.+?)\s+Duration", body, re.IGNORECASE)
    if not name_match:
        log.warning("[gmail] Could not parse company name")
        return None
    company_name = name_match.group(1).strip()

    # ── CMP and Target ────────────────────────────────────────────────────────
    # "CMP Target 182 200" or "CMP 182 Target 200"
    price_match = re.search(
        r"CMP\s+Target\s+([\d.]+)\s+([\d.]+)|CMP\s+([\d.]+)\s+Target\s+([\d.]+)",
        body, re.IGNORECASE
    )
    if not price_match:
        # Try looser: any two numbers after CMP
        price_match = re.search(r"CMP[^\d]+([\d.]+)[^\d]+([\d.]+)", body, re.IGNORECASE)
        if not price_match:
            log.warning("[gmail] Could not parse CMP/Target")
            return None
        cmp_price  = float(price_match.group(1))
        target     = float(price_match.group(2))
    else:
        g = price_match.groups()
        if g[0]:   # "CMP Target 182 200"
            cmp_price, target = float(g[0]), float(g[1])
        else:       # "CMP 182 Target 200"
            cmp_price, target = float(g[2]), float(g[3])

    # ── Stop loss ─────────────────────────────────────────────────────────────
    sl_match = re.search(r"Stop\s*Loss[:\s]+([\d.]+%?)\s+([\d.]+)", body, re.IGNORECASE)
    stop_loss = None
    if sl_match:
        # Could be "Stop Loss 10% 173" — take the absolute price (last number)
        sl_val = sl_match.group(2)
        try:
            stop_loss = float(sl_val)
        except ValueError:
            pass

    # ── NSE symbol lookup ─────────────────────────────────────────────────────
    # Try to map company name to NSE ticker via a simple lookup + yfinance search
    nse_symbol = _resolve_nse_symbol(company_name)
    if not nse_symbol:
        log.warning(f"[gmail] Could not resolve NSE symbol for: {company_name}")
        # Store with a placeholder — user can fix via /add command
        nse_symbol = company_name.upper().replace(" ", "")[:10] + ".NS"

    label = nse_symbol.replace(".NS", "").replace(".BO", "")

    return {
        "symbol":    nse_symbol,
        "label":     label,
        "name":      company_name,
        "buy_date":  received_date.isoformat(),
        "buy_low":   cmp_price,
        "buy_high":  round(cmp_price * 1.005, 2),  # CMP ± 0.5% as buy range
        "target":    target,
        "stop_loss": stop_loss,
        "type":      rec_type,
        "duration_days": duration_days,
        "source":    "axis_direct_email",
    }


def _resolve_nse_symbol(company_name: str) -> str | None:
    """
    Try to find the NSE symbol for a company name.
    Uses Yahoo Finance search API — lightweight, no auth needed.
    """
    try:
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": company_name + " NSE", "quotesCount": 5, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        quotes = resp.json().get("quotes", [])
        for q in quotes:
            sym = q.get("symbol", "")
            exch = q.get("exchange", "")
            # Prefer .NS suffix (NSE) or NSI exchange
            if sym.endswith(".NS") or exch in ("NSI", "NSE"):
                return sym
            # BSE fallback
            if sym.endswith(".BO") or exch == "BSE":
                return sym
    except Exception as e:
        log.error(f"[gmail] Symbol lookup failed for '{company_name}': {e}")
    return None


# ── Main entry point ──────────────────────────────────────────────────────────
def pull_axis_recommendations(recs_path: Path, lookback_days: int = 7) -> list[dict]:
    """
    Search Gmail for recent Axis Direct emails, parse recommendations,
    add new ones to recs_path (skipping duplicates by label+buy_date).
    Returns list of newly added recommendations.
    """
    token = _get_access_token()
    if not token:
        log.warning("[gmail] Skipping email pull — no access token")
        return []

    # Search Gmail for emails from Axis Direct in last lookback_days
    since = (date.today() - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    query = f"from:{AXIS_SENDER} after:{since}"

    log.info(f"[gmail] Searching: {query}")
    search_result = _gmail_get("/messages", token, {"q": query, "maxResults": 20})
    if not search_result:
        return []

    messages = search_result.get("messages", [])
    log.info(f"[gmail] Found {len(messages)} Axis Direct emails")

    # Load existing recs
    existing = json.loads(recs_path.read_text()) if recs_path.exists() else []
    existing_keys = {(r["label"], r["buy_date"]) for r in existing}

    new_recs = []

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        msg = _gmail_get(f"/messages/{msg_id}", token, {"format": "full"})
        if not msg:
            continue

        # Get received date from internal date (milliseconds epoch)
        epoch_ms = int(msg.get("internalDate", 0))
        received_date = date.fromtimestamp(epoch_ms / 1000)

        # Only process research idea emails
        subject = ""
        for header in msg.get("payload", {}).get("headers", []):
            if header["name"].lower() == "subject":
                subject = header["value"]
                break

        if "research" not in subject.lower() and "idea" not in subject.lower() and "alpha" not in subject.lower():
            log.debug(f"[gmail] Skipping non-research email: {subject}")
            continue

        log.info(f"[gmail] Parsing: '{subject}' ({received_date})")
        body = _decode_body(msg)
        rec  = _parse_axis_email(body, received_date)

        if not rec:
            log.warning(f"[gmail] Parse failed for message {msg_id}")
            continue

        key = (rec["label"], rec["buy_date"])
        if key in existing_keys:
            log.info(f"[gmail] Already tracked: {rec['label']} ({rec['buy_date']})")
            continue

        existing.append(rec)
        existing_keys.add(key)
        new_recs.append(rec)
        log.info(f"[gmail] Added: {rec['label']} — Buy ₹{rec['buy_low']}, Target ₹{rec['target']}")

    if new_recs:
        recs_path.parent.mkdir(parents=True, exist_ok=True)
        recs_path.write_text(json.dumps(existing, indent=2))
        log.info(f"[gmail] Saved {len(new_recs)} new recommendations")

    return new_recs
