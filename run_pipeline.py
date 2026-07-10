"""Entry point for cron: scrape → extract signals → generate briefs → push to GitHub.

Designed to be run as a single Railway cron job so the whole pipeline
executes server-side without needing a local machine to be awake.
"""

import asyncio
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(override=True)

from scraper.fetch import fetch_all_channels, save_raw
from signals.extractor import extract_signals, save_signals
from briefs.generator import generate_both, save_brief
from run_brief import push_to_github


async def main():
    print("Scraping Telegram channels...")
    messages = await fetch_all_channels()
    save_raw(messages)
    print(f"  {len(messages)} messages scraped\n")

    raw_messages = [
        {
            "channel": m.channel,
            "message_id": m.message_id,
            "text": m.text,
            "date": m.date.isoformat(),
            "url": m.url,
        }
        for m in messages
    ]

    print("Extracting signals via Claude (Haiku)...")
    signals = await extract_signals(raw_messages)
    save_signals(signals)
    print(f"  {len(signals)} signals extracted\n")

    print("Generating both briefs (Sonnet)...")
    trading_brief, news_digest = await generate_both(signals, raw_messages)

    date_str = datetime.now().strftime("%Y%m%d")
    path1 = save_brief(trading_brief, f"trading_brief_{date_str}.md")
    path2 = save_brief(news_digest, f"news_digest_{date_str}.md")
    print(f"  Saved: {path1}")
    print(f"  Saved: {path2}\n")

    print("Pushing to GitHub...")
    push_to_github(date_str)

    print("\n✅ Pipeline complete.")


if __name__ == "__main__":
    asyncio.run(main())
