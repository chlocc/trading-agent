"""
Daily brief generator.

Reads the latest signals file and produces:
  1. A formatted markdown brief with top themes, bullish/bearish signals, and trade ideas
  2. A saved .md file in data/briefs/
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

from llm import chat

# Brief generation routes through OpenRouter rather than direct Anthropic,
# since the direct Anthropic account ran out of API credit. Brief-writing
# quality benefits from a stronger model than the free extraction default,
# so this uses its own override — defaults to paid Claude Sonnet via
# OpenRouter (billed to the OpenRouter balance, not OPENROUTER_MODEL's free
# tier). Switch OPENROUTER_MODEL_BRIEF or provider="anthropic" below if the
# Anthropic account gets topped up.
OPENROUTER_BRIEF_MODEL = os.environ.get("OPENROUTER_MODEL_BRIEF", "anthropic/claude-sonnet-4.5")

TRADING_BRIEF_PROMPT = """You are a sharp trading desk analyst writing a detailed daily morning brief.

Given a list of extracted trading signals, produce a detailed brief in this exact format:

---
📊 TRADING SIGNALS BRIEF — {date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 TOP THEMES
[3-4 bullet points. For each: name the theme, explain WHY it matters today, and name the key tickers affected.]

🟢 BULLISH SIGNALS
**[TICKER]** — [2-3 sentences: what happened, why it's bullish, what to watch for next. Include source link as (→ source)]
[repeat for each high-confidence bullish signal]

🔴 BEARISH SIGNALS
**[TICKER]** — [2-3 sentences: what happened, why it's bearish, what the downside scenario looks like. Include source link as (→ source)]
[repeat for each high-confidence bearish signal]

💡 TRADE IDEAS
**[#]. [Direction] [Instrument]**
- Rationale: [2-3 sentences explaining the thesis and why now]
- Entry: [suggested entry level or condition]
- Risks: [one sentence on what invalidates this trade]
- Related signals: [bullet list of supporting signals with links]

[5-7 trade ideas total. Mix direct plays, ETF exposure, and pairs trades.
For AI/tech: BOTZ, ARKQ, NVDA, MSFT, GOOG.
For crypto: IBIT, FBTC, ETHA, BITO, COIN, MSTR.]

⚠️ RISKS TO WATCH
[3-4 bullet points. Each should name the risk, the trigger condition, and the potential impact.]

📌 MACRO CONTEXT
[2-3 sentences on broader market backdrop and how it frames today's signals]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{total} signals | {tradeable} tradeable | {bullish} bullish | {bearish} bearish
---

Rules:
- Be detailed but precise — traders need depth, not padding
- Every signal entry must include its source link in (→ https://t.me/...) format
- Trade ideas must have entry conditions and invalidation criteria
- Do not include disclaimers
- Output the brief only, no preamble"""


NEWS_DIGEST_PROMPT = """You are a crypto and tech news editor writing a detailed daily news digest.

Given a list of messages from Telegram channels, categorize every story into sections and write a proper summary for each.
Only include a section if there are actual stories for it — skip empty ones.

Sections (use exactly these headers):
  🏛️ Regulation & Policy
  🤖 AI & Tech
  💳 Payments & Stablecoins
  🏦 Exchanges & Platforms
  📈 Crypto Trading & Markets
  🔷 DeFi & Protocols
  🔦 Other

Format each story as:
  **[Headline]**
  [2-3 sentence summary: what happened, key details/numbers, and why it matters for the space.]
  → [source link]

Rules:
- Every message should appear in exactly one category
- Headlines should be punchy and specific (include numbers/names where possible)
- Summaries must include the key figures, context, and significance — not just restate the headline
- Sort stories within each section by significance (most important first)
- Always include the → source link on its own line after the summary
- Output the digest only, no preamble

---
📰 NEWS DIGEST — {date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[sections here]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
---"""


async def generate_trading_brief(signals: list[dict]) -> tuple[str, dict]:
    tradeable = [s for s in signals if s.get("tradeable")]
    bullish = [s for s in tradeable if s.get("sentiment") == "bullish"]
    bearish = [s for s in tradeable if s.get("sentiment") == "bearish"]
    high_conf = [s for s in tradeable if s.get("confidence") == "high"]
    # Use the date of the most recent signal, not server time (avoids UTC midnight issues)
    dates = [s.get("date", "")[:10] for s in signals if s.get("date")]
    today = max(dates) if dates else datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    today = datetime.strptime(today, "%Y-%m-%d").strftime("%B %d, %Y")

    prompt = TRADING_BRIEF_PROMPT.format(
        date=today,
        total=len(signals),
        tradeable=len(tradeable),
        bullish=len(bullish),
        bearish=len(bearish),
    )

    text, usage = await chat(
        prompt,
        (
            f"High-confidence tradeable signals:\n\n{json.dumps(high_conf, indent=2)}\n\n"
            f"All tradeable signals for context:\n\n{json.dumps(tradeable, indent=2)}"
        ),
        max_tokens=16000,
        anthropic_model="claude-sonnet-4-5",
        provider="openrouter",
        openrouter_model=OPENROUTER_BRIEF_MODEL,
    )
    return text, usage


async def generate_news_digest(raw_messages: list[dict]) -> tuple[str, dict]:
    dates = [m.get("date", "")[:10] for m in raw_messages if m.get("date")]
    today = max(dates) if dates else datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    today = datetime.strptime(today, "%Y-%m-%d").strftime("%B %d, %Y")
    prompt = NEWS_DIGEST_PROMPT.format(date=today)

    # Slim down messages for the digest
    slim = [
        {
            "source": m["channel"],
            "date": m["date"][:10],
            "text": m["text"][:600],
            "url": m.get("url", ""),
        }
        for m in raw_messages
        if m.get("text", "").strip()
    ]

    text, usage = await chat(
        prompt,
        f"Categorize and summarize these messages:\n\n{json.dumps(slim, indent=2)}",
        max_tokens=32000,
        anthropic_model="claude-sonnet-4-5",
        provider="openrouter",
        openrouter_model=OPENROUTER_BRIEF_MODEL,
    )
    return text, usage


async def generate_both(signals: list[dict], raw_messages: list[dict]) -> tuple[str, str]:
    """Generate both briefs in parallel."""
    print(f"  Model: {OPENROUTER_BRIEF_MODEL} (via OpenRouter)")
    (trading_brief, trading_usage), (news_digest, news_usage) = await asyncio.gather(
        generate_trading_brief(signals),
        generate_news_digest(raw_messages),
    )

    usage_totals = {k: trading_usage[k] + news_usage[k] for k in trading_usage}

    # Briefs route through OpenRouter (see OPENROUTER_BRIEF_MODEL above) —
    # its $/token rate isn't wired up here, so report usage only rather
    # than a cost computed from stale direct-Anthropic pricing.
    cost_str = f"(via OpenRouter, model={OPENROUTER_BRIEF_MODEL}, cost billed to OpenRouter balance)"

    print(
        f"\n  💰 Brief generation usage: in={usage_totals['input']} "
        f"cache_write={usage_totals['cache_write']} cache_read={usage_totals['cache_read']} "
        f"out={usage_totals['output']} | est. cost: {cost_str}"
    )

    return trading_brief, news_digest


def save_brief(content: str, filename: str, out_dir: str = "data/briefs") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(out_dir) / filename
    out_path.write_text(content, encoding="utf-8")
    return out_path


def load_latest_signals(processed_dir: str = "data/processed") -> list[dict]:
    files = sorted(Path(processed_dir).glob("signals_*.json"))
    if not files:
        raise FileNotFoundError("No signal files found in data/processed/")
    latest = files[-1]
    print(f"  Loading signals: {latest.name}")
    return json.loads(latest.read_text())


def load_latest_raw(raw_dir: str = "data/raw") -> list[dict]:
    files = sorted(Path(raw_dir).glob("messages_*.json"))
    if not files:
        raise FileNotFoundError("No raw message files found in data/raw/")
    latest = files[-1]
    print(f"  Loading messages: {latest.name}")
    return json.loads(latest.read_text())
