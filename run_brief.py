"""Entry point: generate both daily briefs from latest signals + raw messages."""

import asyncio
import subprocess
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(override=True)

from briefs.generator import generate_both, load_latest_signals, load_latest_raw, save_brief


def push_to_github(date_str: str):
    """Auto-commit and push new briefs to GitHub so Railway serves them."""
    try:
        subprocess.run(["git", "add", "data/briefs/"], check=True)
        subprocess.run(["git", "commit", "-m", f"Auto: briefs for {date_str}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Pushed to GitHub — Railway will update shortly")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Git push failed: {e} (briefs saved locally)")


async def main():
    print("Loading data...")
    signals = load_latest_signals()
    messages = load_latest_raw()
    print(f"  {len(signals)} signals | {len(messages)} raw messages\n")

    print("Generating both briefs in parallel...")
    trading_brief, news_digest = await generate_both(signals, messages)

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

    print("\nPushing to GitHub...")
    push_to_github(date_str)


if __name__ == "__main__":
    asyncio.run(main())
