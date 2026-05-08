"""
hedge_analyzer.py
Uses Claude API to generate practical NSE options hedging suggestions
for a tracked equity position, given its current price.
"""

import os
import logging
from datetime import date, datetime

import anthropic

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a concise financial analyst specializing in Indian equity markets (NSE/BSE). "
    "You give practical, actionable hedging advice using NSE-listed options. "
    "You always mention lot sizes, approximate premium ranges, and specific strikes. "
    "You note when stock options are illiquid and suggest index (Nifty/BankNifty) hedges instead. "
    "You never give open-ended advice — always commit to 2-3 specific strategies. "
    "Output plain text only, no markdown, under 260 words."
)


def _position_prompt(rec: dict, current_price: float | None) -> str:
    buy_price = rec["buy_low"]
    days_held = (date.today() - datetime.strptime(rec["buy_date"], "%Y-%m-%d").date()).days

    lines = [
        f"Stock: {rec['name']} ({rec['label']}, NSE: {rec['symbol']})",
        f"Buy price: ₹{buy_price}–{rec['buy_high']}",
        f"Buy date: {rec['buy_date']} ({days_held} days held)",
        f"Trade type: {rec['type']}",
    ]
    if rec.get("source"):
        lines.append(f"Source: {rec['source']}")
    if rec.get("target"):
        lines.append(f"Target: ₹{rec['target']}")
    if current_price:
        pnl = (current_price - buy_price) / buy_price * 100
        sign = "+" if pnl >= 0 else ""
        lines.append(f"Current price: ₹{current_price:.2f} ({sign}{pnl:.1f}% vs buy)")

    position_block = "\n".join(lines)

    return (
        f"A retail client holds this long equity position and wants to hedge it using options only:\n\n"
        f"{position_block}\n\n"
        "Suggest 2-3 concrete hedging strategies. For each:\n"
        "1. Exact action: buy/sell, which instrument (stock options or Nifty puts), "
        "which strike, nearest monthly/weekly expiry, approximate premium\n"
        "2. What risk it hedges (downside loss, theta bleed, gap-down, etc.)\n"
        "3. Trade-off in one sentence\n\n"
        "End with a one-line recommendation on which strategy fits best given the position size and type."
    )


async def analyze_hedge(rec: dict, current_price: float | None) -> str:
    """
    Returns a Telegram HTML-formatted hedging analysis string.
    Returns None if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("[hedge] ANTHROPIC_API_KEY not set — skipping hedge analysis")
        return None

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=450,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _position_prompt(rec, current_price)}],
        )
        analysis = msg.content[0].text.strip()
    except Exception as e:
        log.error(f"[hedge] Claude API error: {e}")
        return None

    buy_price = rec["buy_low"]
    days_held = (date.today() - datetime.strptime(rec["buy_date"], "%Y-%m-%d").date()).days

    header_parts = [f"🛡️ <b>Hedge Suggestions — {rec['label']}</b>"]
    if current_price:
        pnl = (current_price - buy_price) / buy_price * 100
        sign = "+" if pnl >= 0 else ""
        em = "🟢" if pnl >= 0 else "🔴"
        header_parts.append(
            f"{em} {rec['name']} · {days_held}d held · ₹{current_price:.2f} ({sign}{pnl:.1f}%)"
        )
    else:
        header_parts.append(f"⚪ {rec['name']} · {days_held}d held · price unavailable")

    header = "\n".join(header_parts) + "\n\n"
    footer = "\n\n<i>⚠️ Not SEBI-registered advice. Verify strikes and premiums on NSE before trading.</i>"

    return header + analysis + footer
