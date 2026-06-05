"""Telegram Bot API client using httpx (no Telethon needed)."""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.telegram.org/bot{token}/{method}"


def get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")
    return token


async def bot_get(method: str, **params) -> dict:
    """Make an async GET request to the Bot API."""
    url = BASE_URL.format(token=get_token(), method=method)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params={k: v for k, v in params.items() if v is not None})
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Bot API error: {data.get('description')}")
        return data["result"]
