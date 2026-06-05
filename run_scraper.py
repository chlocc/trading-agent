"""Entry point: scrape all configured channels and save raw output."""

import asyncio
import sys
from dotenv import load_dotenv
load_dotenv(override=True)
from scraper.fetch import fetch_all_channels, save_raw


async def main():
    print("Scraping Telegram channels...")
    messages = await fetch_all_channels()
    out_path = save_raw(messages)
    print(f"\nDone. {len(messages)} messages saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
