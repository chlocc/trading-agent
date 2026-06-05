"""Entry point: generate both daily briefs from latest signals + raw messages."""

import asyncio
from dotenv import load_dotenv
load_dotenv(override=True)

from briefs.generator import generate_both, load_latest_signals, load_latest_raw, save_brief


async def main():
    print("Loading data...")
    signals = load_latest_signals()
    messages = load_latest_raw()
    print(f"  {len(signals)} signals | {len(messages)} raw messages\n")

    print("Generating both briefs in parallel...")
    trading_brief, news_digest = await generate_both(signals, messages)

    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")

    path1 = save_brief(trading_brief, f"trading_brief_{date_str}.md")
    path2 = save_brief(news_digest, f"news_digest_{date_str}.md")

    print(f"\n{'='*60}")
    print(trading_brief)
    print(f"\n{'='*60}")
    print(news_digest)
    print(f"{'='*60}")
    print(f"\n✅ Saved:")
    print(f"   {path1}")
    print(f"   {path2}")


if __name__ == "__main__":
    asyncio.run(main())
