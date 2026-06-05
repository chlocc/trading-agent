"""Entry point: extract signals from the latest raw scrape."""

import asyncio
from dotenv import load_dotenv
load_dotenv(override=True)
from signals.extractor import extract_signals, load_latest_raw, save_signals


async def main():
    print("Loading latest raw messages...")
    messages = load_latest_raw()
    print(f"  {len(messages)} messages loaded\n")

    print("Extracting signals via Claude...")
    signals = await extract_signals(messages)

    # Quick summary
    tradeable = [s for s in signals if s.get("tradeable")]
    bullish = [s for s in tradeable if s.get("sentiment") == "bullish"]
    bearish = [s for s in tradeable if s.get("sentiment") == "bearish"]
    high_conf = [s for s in tradeable if s.get("confidence") == "high"]

    out_path = save_signals(signals)
    print(f"\n{'='*50}")
    print(f"  Total signals:     {len(signals)}")
    print(f"  Tradeable:         {len(tradeable)}")
    print(f"  Bullish / Bearish: {len(bullish)} / {len(bearish)}")
    print(f"  High confidence:   {len(high_conf)}")
    print(f"  Saved to:          {out_path}")
    print(f"{'='*50}\n")

    print("Top signals:")
    for s in sorted(high_conf, key=lambda x: x.get("sentiment") == "bullish", reverse=True)[:5]:
        icon = "🟢" if s["sentiment"] == "bullish" else "🔴" if s["sentiment"] == "bearish" else "⚪"
        tickers = ", ".join(s.get("tickers", [])) or "—"
        print(f"  {icon} [{s['channel']}] {tickers} | {s['summary']}")


if __name__ == "__main__":
    asyncio.run(main())
