"""Data models for scraped messages."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChannelMessage:
    channel: str
    message_id: int
    text: str
    date: datetime
    views: int | None = None
    forwards: int | None = None
    has_media: bool = False
    media_type: str | None = None  # "photo", "document", "video", etc.
    url: str | None = None
