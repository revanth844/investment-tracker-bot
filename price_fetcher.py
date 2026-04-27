"""
price_fetcher.py
Multi-source price fetcher with waterfall fallback:

  Source 1: NSE Bhavcopy (official NSE daily CSV — zero rate limits, official data)
            URL: https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_*.csv
            Covers: all NSE equities + indices, published ~6 PM IST daily
            Limit:  none — static file per trading day

  Source 2: openchart (NSE's own chart backend, same data powering nseindia.com charts)
            pip install openchart
            Covers: NSE equities + indices, intraday + EOD
            Limit:  very lenient, no API key needed

  Source 3: Yahoo Finance (yfinance) — kept as last resort
            Limit:  aggressive rate-limiting on cloud IPs (reason we're here)

Waterfall: try Source 1 → if empty, try Source 2 → if empty, try Source 3
Result is always (dates: list[date], closes: list[float]) or ([], []) on total failure.
"""

import time
import random
import logging
import requests
import zipfile
import io
import csv
from datetime import datetime, date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# ── NSE symbol maps ───────────────────────────────────────────────────────────
# Bhavcopy uses bare NSE symbols (no .NS suffix)
# openchart uses "SYMBOL-EQ" for equities, index names for indices

BHAVCOPY_INDEX_SYMBOLS = {
    "^NSEI":  "Nifty 50",
    "^BSESN": None,           # Sensex is BSE — not in NSE Bhavcopy, use openchart
}

OPENCHART_SYMBOL_MAP = {
    # Yahoo symbol  → (openchart_symbol,  segment)
    "^NSEI":        ("NIFTY",             "NSE"),   # Nifty 50 index
    "^BSESN":       ("SENSEX",            "BSE"),   # Sensex index
}

def _strip_suffix(symbol: str) -> str:
    """RELIANCE.NS → RELIANCE"""
    return symbol.replace(".NS", "").replace(".BO", "").replace(".BSE", "")

def _to_openchart_symbol(yahoo_symbol: str) -> tuple[str, str]:
    """Map Yahoo symbol to (openchart_symbol, exchange)."""
    if yahoo_symbol in OPENCHART_SYMBOL_MAP:
        return OPENCHART_SYMBOL_MAP[yahoo_symbol]
    bare = _strip_suffix(yahoo_symbol)
    return f"{bare}-EQ", "NSE"


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 1: NSE Bhavcopy
# ═══════════════════════════════════════════════════════════════════════════════

BHAVCOPY_BASE = "https://nsearchives.nseindia.com/content/cm"
NSE_HEADERS   = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://www.nseindia.com/",
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _bhavcopy_url(dt: date) -> str:
    """Return Bhavcopy ZIP URL for a given date."""
    # New UDIFF format (post July 8 2024):
    # BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
    ds = dt.strftime("%Y%m%d")
    return f"{BHAVCOPY_BASE}/BhavCopy_NSE_CM_0_0_0_{ds}_F_0000.csv.zip"

def _fetch_bhavcopy_day(dt: date, session: requests.Session) -> dict[str, float]:
    """
    Download and parse NSE Bhavcopy for one trading day.
    Returns {SYMBOL: close_price} for all equities in EQ series.
    Returns {} on failure (holiday, weekend, or fetch error).
    """
    url = _bhavcopy_url(dt)
    try:
        resp = session.get(url, timeout=15, headers=NSE_HEADERS)
        if resp.status_code == 404:
            return {}  # holiday / non-trading day
        resp.raise_for_status()

        # Parse ZIP → CSV
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            fname = zf.namelist()[0]
            with zf.open(fname) as f:
                reader = csv.DictReader(io.TextIOWrapper(f))
                prices = {}
                for row in reader:
                    # Only EQ series (not BE, SM, etc.)
                    if row.get("SctySrs", "").strip() == "EQ":
                        sym   = row.get("TckrSymb", "").strip()
                        close = row.get("ClsPric", "") or row.get("LastPric", "")
                        if sym and close:
                            try:
                                prices[sym] = float(close)
                            except ValueError:
                                pass
        return prices

    except Exception as e:
        log.debug(f"Bhavcopy fetch failed for {dt}: {e}")
        return {}

def _index_close_from_bhavcopy(dt: date, index_name: str, session: requests.Session) -> float | None:
    """Fetch Nifty/Bank Nifty close from NSE index Bhavcopy CSV."""
    ds  = dt.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{ds}.csv"
    try:
        resp = session.get(url, timeout=15, headers=NSE_HEADERS)
        if resp.status_code != 200:
            return None
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            if row.get("Index Name", "").strip().upper() == index_name.upper():
                close = row.get("Closing Index Value", "")
                return float(close) if close else None
    except Exception as e:
        log.debug(f"Index Bhavcopy failed for {dt}/{index_name}: {e}")
    return None

def fetch_bhavcopy(yahoo_symbol: str, start: str) -> tuple[list, list]:
    """
    Build a daily close price series via NSE Bhavcopy CSVs.
    Downloads one ZIP per trading day — very reliable, official source.
    """
    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    today    = date.today()
    bare     = _strip_suffix(yahoo_symbol)

    # Determine if this is an index
    is_nifty  = yahoo_symbol == "^NSEI"
    is_sensex = yahoo_symbol == "^BSESN"

    if is_sensex:
        return [], []  # Sensex not in NSE Bhavcopy → skip to Source 2

    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    dates, closes = [], []
    current = start_dt

    log.info(f"[Bhavcopy] fetching {yahoo_symbol} from {start_dt} to {today}")
    while current <= today:
        # Skip weekends
        if current.weekday() < 5:
            if is_nifty:
                price = _index_close_from_bhavcopy(current, "Nifty 50", session)
            else:
                day_prices = _fetch_bhavcopy_day(current, session)
                price = day_prices.get(bare)

            if price is not None:
                dates.append(current)
                closes.append(price)

            time.sleep(0.3)  # polite delay — static files so 300ms is plenty

        current += timedelta(days=1)

    if dates:
        log.info(f"[Bhavcopy] {yahoo_symbol}: {len(dates)} days, {dates[0]}→{dates[-1]}")
    else:
        log.warning(f"[Bhavcopy] {yahoo_symbol}: no data returned")

    return dates, closes


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2: openchart (NSE chart backend)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_openchart(yahoo_symbol: str, start: str) -> tuple[list, list]:
    """
    Fetch via openchart library — uses NSE's own chart data backend.
    No API key, no rate-limit issues.
    """
    try:
        from openchart import NSEData  # pip install openchart
    except ImportError:
        log.warning("[openchart] not installed — skipping. Add 'openchart' to requirements.txt")
        return [], []

    start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    oc_sym, exchange = _to_openchart_symbol(yahoo_symbol)

    try:
        nse = NSEData()
        nse.download()  # downloads/updates master symbol list (cached)

        df = nse.historical(
            symbol    = oc_sym,
            exchange  = exchange,
            start     = datetime.combine(start_dt, datetime.min.time()),
            end       = datetime.combine(date.today(), datetime.min.time()),
            timeframe = "1d",
        )

        if df is None or df.empty:
            log.warning(f"[openchart] {yahoo_symbol}: empty response")
            return [], []

        df = df.sort_index()
        dates  = [d.date() for d in df.index]
        closes = df["Close"].tolist()
        log.info(f"[openchart] {yahoo_symbol}: {len(dates)} days, {dates[0]}→{dates[-1]}")
        return dates, closes

    except Exception as e:
        log.error(f"[openchart] {yahoo_symbol} failed: {e}")
        return [], []


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 3: Yahoo Finance (last resort)
# ═══════════════════════════════════════════════════════════════════════════════

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]
RETRY_WAITS = [20, 45, 90]

def fetch_yahoo(yahoo_symbol: str, start: str, retries: int = 3) -> tuple[list, list]:
    """Yahoo Finance with aggressive backoff — last resort only."""
    try:
        import yfinance as yf
    except ImportError:
        log.warning("[yahoo] yfinance not installed")
        return [], []

    start_dt = datetime.strptime(start, "%Y-%m-%d").date()

    for attempt in range(retries):
        wait = RETRY_WAITS[attempt] + random.uniform(0, 10)
        if attempt > 0:
            log.info(f"[yahoo] {yahoo_symbol}: waiting {wait:.0f}s before retry {attempt+1}...")
            time.sleep(wait)
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
            tk = yf.Ticker(yahoo_symbol, session=session)
            df = tk.history(start=start, interval="1d", auto_adjust=True, timeout=20)
            if df is None or df.empty:
                log.warning(f"[yahoo] {yahoo_symbol} attempt {attempt+1}: empty")
                continue
            df.index = df.index.tz_localize(None)
            dates  = [d.date() for d in df.index if d.date() >= start_dt]
            closes = [float(df.loc[df.index.date == d, "Close"].iloc[0]) for d in dates]
            if dates:
                log.info(f"[yahoo] {yahoo_symbol}: {len(dates)} days")
                return dates, closes
        except Exception as e:
            log.error(f"[yahoo] {yahoo_symbol} attempt {attempt+1}: {e}")

    return [], []


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC INTERFACE — waterfall fetch
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_prices(yahoo_symbol: str, start: str) -> tuple[list, list]:
    """
    Fetch historical daily closes with 3-source waterfall:
      1. NSE Bhavcopy  (official, zero rate limit)
      2. openchart     (NSE chart backend, very lenient)
      3. Yahoo Finance (last resort, rate-limited)

    Returns (dates: list[date], closes: list[float]) or ([], []) on total failure.
    The symbol format is always Yahoo-style: RELIANCE.NS, ^NSEI, ^BSESN
    """
    log.info(f"[fetch] {yahoo_symbol} from {start}")

    # Source 1: Bhavcopy (skip for Sensex — not on NSE)
    dates, closes = fetch_bhavcopy(yahoo_symbol, start)
    if dates:
        log.info(f"[fetch] {yahoo_symbol} ✓ via Bhavcopy ({len(dates)} days)")
        return dates, closes

    # Source 2: openchart
    log.info(f"[fetch] {yahoo_symbol}: Bhavcopy empty → trying openchart")
    dates, closes = fetch_openchart(yahoo_symbol, start)
    if dates:
        log.info(f"[fetch] {yahoo_symbol} ✓ via openchart ({len(dates)} days)")
        return dates, closes

    # Source 3: Yahoo Finance
    log.warning(f"[fetch] {yahoo_symbol}: openchart empty → trying Yahoo Finance (rate-limited)")
    dates, closes = fetch_yahoo(yahoo_symbol, start)
    if dates:
        log.info(f"[fetch] {yahoo_symbol} ✓ via Yahoo Finance ({len(dates)} days)")
        return dates, closes

    log.error(f"[fetch] {yahoo_symbol}: ALL 3 sources failed")
    return [], []
