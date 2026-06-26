"""
Signal extraction via Claude.

For each batch of messages, Claude returns structured signals:
  - tickers mentioned (BTC, ETH, COIN, etc.)
  - theme (DeFi, stablecoin, regulation, AI/tech, macro, etc.)
  - sentiment (bullish / bearish / neutral)
  - confidence (high / medium / low)
  - one-line summary

Uses prompt caching on the system prompt to minimize API costs.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import asyncio
import re
import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

SYSTEM_PROMPT = """You are a crypto and tech-equity trading signal extractor.

Given a list of Telegram channel messages, extract structured trading signals.

For each message return a JSON object with:
  - message_id: (integer, from input)
  - channel: (string, from input)
  - url: (string, from input — pass through unchanged)
  - tickers: list of relevant ticker symbols (crypto: BTC, ETH, SOL etc; stocks: COIN, MSTR, NVDA etc). Empty list if none.
  - theme: one of [DeFi, stablecoin, regulation, macro, AI/tech, exchange, NFT/gaming, layer2, other]
  - sentiment: one of [bullish, bearish, neutral]
  - confidence: one of [high, medium, low]
  - summary: one crisp sentence capturing the signal
  - tradeable: true if this could inform a trade, false if it's noise/irrelevant

Respond with a JSON array only — no markdown, no explanation, just the array.

Guidelines:
- Be conservative with confidence: only "high" if the signal is very clear
- Tickers: include both direct mentions AND strongly implied ones (e.g. a Coinbase story implies COIN)
- For AI/tech stories, consider NVDA, MSFT, GOOG, and AI-adjacent ETFs like BOTZ, ARKQ
- Mark tradeable=false for generic news, price recaps, or announcements with no clear directional signal"""


async def extract_signals(messages: list[dict]) -> list[dict]:
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Process in batches of 20 to stay within context limits
    batch_size = 20
    all_signals = []

    for i in range(0, len(messages), batch_size):
        batch = messages[i : i + batch_size]
        print(f"  Extracting signals from messages {i+1}–{min(i+batch_size, len(messages))}...")

        # Strip to just what Claude needs
        slim = [
            {
                "message_id": m["message_id"],
                "channel": m["channel"],
                "date": m["date"][:10],
                "text": m["text"][:800],
                "url": m.get("url", ""),
            }
            for m in batch
        ]

        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # cache system prompt
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Extract signals from these messages:\n\n{json.dumps(slim, indent=2)}",
                }
            ],
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        try:
            signals = json.loads(raw)
            all_signals.extend(signals)
        except json.JSONDecodeError as e:
            print(f"    ✗ JSON parse error on batch {i//batch_size + 1}: {e}")
            print(f"    Raw response: {raw[:200]}")

        # Small delay between batches to avoid rate limits
        if i + batch_size < len(messages):
            await asyncio.sleep(5)

    return all_signals


def save_signals(signals: list[dict], out_dir: str = "data/processed") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(out_dir) / f"signals_{timestamp}.json"
    out_path.write_text(json.dumps(signals, indent=2, ensure_ascii=False))
    return out_path


def load_latest_raw(raw_dir: str = "data/raw") -> list[dict]:
    raw_files = sorted(Path(raw_dir).glob("messages_*.json"))
    if not raw_files:
        raise FileNotFoundError("No raw message files found in data/raw/")
    latest = raw_files[-1]
    print(f"  Loading {latest.name}")
    return json.loads(latest.read_text())
