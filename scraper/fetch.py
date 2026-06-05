"""
Scrape public Telegram channels via t.me/s/{channel} (no auth required).

Telegram's web preview exposes all posts from any public channel at:
  https://t.me/s/{channel}

This requires no bot membership, no API credentials, and no Telethon.
It works for any channel with a public username.
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path

import httpx

from .models import ChannelMessage

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _parse_messages(channel: str, html: str) -> list[ChannelMessage]:
    messages = []

    # Each post is wrapped in a <div class="tgme_widget_message_wrap ...">
    # Extract message blocks
    blocks = re.findall(
        r'<div class="tgme_widget_message_wrap[^"]*".*?(?=<div class="tgme_widget_message_wrap|$)',
        html,
        re.DOTALL,
    )

    for block in blocks:
        # Message ID
        id_match = re.search(r'data-post="[^/]+/(\d+)"', block)
        if not id_match:
            continue
        message_id = int(id_match.group(1))

        # Text content — strip HTML tags
        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            block,
            re.DOTALL,
        )
        if not text_match:
            continue
        raw_text = text_match.group(1)
        # Convert <br> to newlines, strip remaining tags
        text = re.sub(r"<br\s*/?>", "\n", raw_text)
        text = re.sub(r"<[^>]+>", "", text)
        text = unescape(text).strip()
        if not text:
            continue

        # Timestamp
        date = datetime.now(tz=timezone.utc)  # fallback
        time_match = re.search(r'datetime="([^"]+)"', block)
        if time_match:
            try:
                date = datetime.fromisoformat(time_match.group(1).replace("Z", "+00:00"))
            except ValueError:
                pass

        # Views
        views = None
        views_match = re.search(r'class="tgme_widget_message_views"[^>]*>([\d.,KkMm]+)<', block)
        if views_match:
            raw_v = views_match.group(1).replace(",", "").upper()
            try:
                if "K" in raw_v:
                    views = int(float(raw_v.replace("K", "")) * 1000)
                elif "M" in raw_v:
                    views = int(float(raw_v.replace("M", "")) * 1_000_000)
                else:
                    views = int(raw_v)
            except ValueError:
                pass

        has_media = bool(re.search(r'tgme_widget_message_photo|tgme_widget_message_video', block))

        tg_link = f"https://t.me/{channel.lstrip('@')}/{message_id}"
        messages.append(ChannelMessage(
            channel=f"@{channel.lstrip('@')}",
            message_id=message_id,
            text=text,
            date=date,
            views=views,
            has_media=has_media,
            url=tg_link,
        ))

    return messages


async def fetch_channel(channel: str, limit: int = 100) -> list[ChannelMessage]:
    channel = channel.lstrip("@")
    url = f"https://t.me/s/{channel}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            messages = _parse_messages(channel, resp.text)
            return messages[:limit]
        else:
            raise RuntimeError(
                f"Failed to fetch {url}: HTTP {resp.status_code}. "
                "Is the channel username correct and public?"
            )


async def fetch_all_channels(limit: int | None = None) -> list[ChannelMessage]:
    channels_raw = os.environ.get("TELEGRAM_CHANNELS", "")
    channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    if not channels:
        raise ValueError("TELEGRAM_CHANNELS is empty — set it in .env")

    per_channel_limit = limit or int(os.environ.get("MESSAGES_LIMIT", "100"))

    # Only keep messages from last 24 hours (9:30am yesterday → 9:30am today)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    all_messages: list[ChannelMessage] = []

    for channel in channels:
        print(f"  Fetching @{channel.lstrip('@')}...")
        try:
            msgs = await fetch_channel(channel, per_channel_limit)
            filtered = [m for m in msgs if m.date >= cutoff]
            all_messages.extend(filtered)
            print(f"    → {len(filtered)} messages (last 21h, {len(msgs)-len(filtered)} older skipped)")
        except Exception as e:
            print(f"    ✗ Failed: {e}")

    return all_messages


def save_raw(messages: list[ChannelMessage], out_dir: str = "data/raw") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(out_dir) / f"messages_{timestamp}.json"

    records = [
        {
            "channel": m.channel,
            "message_id": m.message_id,
            "text": m.text,
            "date": m.date.isoformat(),
            "views": m.views,
            "forwards": m.forwards,
            "has_media": m.has_media,
            "media_type": m.media_type,
            "url": m.url,
        }
        for m in messages
    ]

    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    return out_path
