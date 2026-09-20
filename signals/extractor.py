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
from dotenv import load_dotenv

load_dotenv(override=True)

from llm import chat

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


# Haiku 4.5 pricing per million tokens (update if pricing changes)
PRICE_PER_MTOK = {
    "input": 1.00,
    "cache_write": 1.25,
    "cache_read": 0.10,
    "output": 5.00,
}


async def extract_signals(messages: list[dict]) -> list[dict]:
    from llm import DEFAULT_OPENROUTER_MODEL

    openrouter_model = os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    print(f"  Model: {openrouter_model} (via OpenRouter)")

    # Process in batches of 20 to stay within context limits
    batch_size = 20
    all_signals = []
    usage_totals = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}

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

        # deepseek-v4-flash-0731 spends part of its budget on internal
        # reasoning before writing the JSON array, which can truncate the
        # output mid-batch (invalid/incomplete JSON) even with a raised
        # max_tokens. Retry the same batch a couple times before giving up,
        # rather than silently dropping those messages.
        for parse_attempt in range(3):
            raw, usage = await chat(
                SYSTEM_PROMPT,
                f"Extract signals from these messages:\n\n{json.dumps(slim, indent=2)}",
                max_tokens=16000,
                anthropic_model="claude-haiku-4-5",
                provider="openrouter",
                openrouter_model=openrouter_model,
            )

            for key in usage_totals:
                usage_totals[key] += usage[key]
            print(
                f"    tokens: in={usage['input']} cache_write={usage['cache_write']} "
                f"cache_read={usage['cache_read']} out={usage['output']}"
            )

            # Strip markdown code fences if present
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned).strip()
            try:
                signals = json.loads(cleaned)
                all_signals.extend(signals)
                break
            except json.JSONDecodeError as e:
                print(f"    ✗ JSON parse error on batch {i//batch_size + 1}, attempt {parse_attempt + 1}: {e}")
                if parse_attempt == 2:
                    print(f"    ✗ giving up on batch {i//batch_size + 1} after 3 attempts — messages dropped")
                    print(f"    Raw response: {cleaned[:200]}")
                else:
                    await asyncio.sleep(5)

        # Small delay between batches to avoid rate limits
        if i + batch_size < len(messages):
            await asyncio.sleep(5)

    # Extraction runs on OpenRouter, whose $/token rate isn't wired up here
    # — report usage only rather than a cost computed from stale Anthropic
    # Haiku pricing.
    cost_str = f"(via OpenRouter, model={openrouter_model}, cost billed to OpenRouter balance)"
    print(
        f"\n  💰 Signal extraction usage: in={usage_totals['input']} "
        f"cache_write={usage_totals['cache_write']} cache_read={usage_totals['cache_read']} "
        f"out={usage_totals['output']} | est. cost: {cost_str}"
    )

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
