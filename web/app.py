"""Simple Flask dashboard for trading briefs."""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import markdown2
from flask import Flask, render_template_string, abort

app = Flask(__name__)

BRIEFS_DIR = Path(__file__).parent.parent / "data" / "briefs"


def get_available_dates():
    """Return sorted list of dates that have briefs, newest first."""
    dates = set()
    for f in BRIEFS_DIR.glob("trading_brief_*.md"):
        m = re.search(r"(\d{8})", f.name)
        if m:
            dates.add(m.group(1))
    return sorted(dates, reverse=True)


def format_date(date_str):
    """Format 20260604 -> June 04, 2026"""
    try:
        return datetime.strptime(date_str, "%Y%m%d").strftime("%B %d, %Y")
    except ValueError:
        return date_str


def linkify_tg(html: str) -> str:
    """Convert (→ https://t.me/...) and → https://t.me/... patterns to clickable Telegram links."""
    # Match (→ https://t.me/channel/id) pattern
    html = re.sub(
        r'\(→\s*(https://t\.me/[^\s\)]+)\)',
        r'<a href="\1" target="_blank" rel="noopener" class="tg-link">→ Telegram</a>',
        html
    )
    # Match bare → https://t.me/... pattern
    html = re.sub(
        r'→\s*(https://t\.me/[^\s<\)]+)',
        r'<a href="\1" target="_blank" rel="noopener" class="tg-link">→ Telegram</a>',
        html
    )
    return html


def load_brief(date_str, brief_type):
    path = BRIEFS_DIR / f"{brief_type}_{date_str}.md"
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    # Strip leading/trailing --- separators
    content = re.sub(r"^---\n", "", content).strip()
    content = re.sub(r"\n---$", "", content).strip()
    html = markdown2.markdown(
        content,
        extras=["strike", "tables", "break-on-newline", "cuddled-lists"]
    )
    return linkify_tg(html)


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daily Crypto Brief{% if date %} — {{ formatted_date }}{% endif %}</title>
  <style>
    :root {
      --bg: #0f1117;
      --surface: #1a1d27;
      --border: #2a2d3a;
      --text: #e2e8f0;
      --muted: #8892a4;
      --green: #22c55e;
      --red: #ef4444;
      --yellow: #f59e0b;
      --blue: #3b82f6;
      --accent: #6366f1;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      line-height: 1.7;
    }

    /* Nav */
    nav {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 0 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 56px;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .nav-brand {
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      text-decoration: none;
      letter-spacing: -0.3px;
    }
    .nav-brand span { color: var(--accent); }
    .date-nav {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .date-nav a {
      color: var(--muted);
      text-decoration: none;
      font-size: 13px;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--border);
      transition: all 0.15s;
    }
    .date-nav a:hover, .date-nav a.active {
      color: var(--text);
      background: var(--border);
      border-color: var(--accent);
    }

    /* Layout */
    .container {
      max-width: 1100px;
      margin: 0 auto;
      padding: 40px 24px;
    }

    /* Disclaimer */
    .disclaimer {
      font-size: 11px;
      color: var(--muted);
      text-align: center;
      margin-bottom: 16px;
      letter-spacing: 0.3px;
    }

    /* Tabs */
    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 32px;
      border-bottom: 1px solid var(--border);
    }
    .tab {
      padding: 10px 20px;
      cursor: pointer;
      color: var(--muted);
      font-size: 14px;
      font-weight: 500;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: all 0.15s;
      text-decoration: none;
    }
    .tab:hover { color: var(--text); }
    .tab.active {
      color: var(--text);
      border-bottom-color: var(--accent);
    }

    /* Brief content */
    .brief-content h1 {
      font-size: 22px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .brief-content h2 {
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      margin: 32px 0 16px;
      padding: 10px 14px;
      background: var(--surface);
      border-radius: 8px;
      border-left: 3px solid var(--accent);
    }
    .brief-content h3 {
      font-size: 15px;
      font-weight: 600;
      color: var(--text);
      margin: 24px 0 8px;
    }
    .brief-content p {
      margin-bottom: 12px;
      color: var(--text);
    }
    .brief-content ul, .brief-content ol {
      margin: 8px 0 16px 20px;
    }
    .brief-content li {
      margin-bottom: 8px;
      color: var(--text);
    }
    .brief-content strong { color: #fff; }
    .brief-content a {
      color: var(--blue);
      text-decoration: none;
    }
    .tg-link {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      color: #29b6f6 !important;
      font-size: 12px;
      font-weight: 500;
      background: rgba(41,182,246,0.1);
      padding: 2px 8px;
      border-radius: 4px;
      border: 1px solid rgba(41,182,246,0.25);
      text-decoration: none !important;
      transition: all 0.15s;
      cursor: pointer;
    }
    .tg-link:hover {
      background: rgba(41,182,246,0.25);
      border-color: rgba(41,182,246,0.5);
    }
    .brief-content hr {
      border: none;
      border-top: 1px solid var(--border);
      margin: 32px 0;
    }
    /* Emoji section headers */
    .brief-content p:has(> strong:only-child) {
      background: var(--surface);
      padding: 10px 14px;
      border-radius: 8px;
      border-left: 3px solid var(--accent);
    }

    /* Empty state */
    .empty {
      text-align: center;
      padding: 80px 20px;
      color: var(--muted);
    }
    .empty h2 { font-size: 20px; margin-bottom: 8px; color: var(--text); }

    /* Footer */
    footer {
      text-align: center;
      padding: 32px;
      color: var(--muted);
      font-size: 13px;
      border-top: 1px solid var(--border);
      margin-top: 60px;
    }
  </style>
</head>
<body>

<nav>
  <a class="nav-brand" href="/"><span>◈</span> Daily Crypto Brief</a>
  <div class="date-nav">
    {% for d in all_dates[:7] %}
    <a href="/{{ d }}" class="{{ 'active' if d == date else '' }}">
      {{ d[4:6] }}/{{ d[6:] }}/{{ d[:4] }}
    </a>
    {% endfor %}
  </div>
</nav>

<div class="container">
  {% if not date %}
    {% if all_dates %}
      <script>window.location = "/{{ all_dates[0] }}";</script>
    {% else %}
      <div class="empty">
        <h2>No briefs yet</h2>
        <p>Run <code>python3 run_brief.py</code> to generate today's brief.</p>
      </div>
    {% endif %}
  {% else %}
    <p class="disclaimer">Not investment advice. Not legal advice. Always do your own research.</p>
    <div class="tabs">
      <a class="tab {{ 'active' if tab == 'trading' else '' }}"
         href="/{{ date }}/trading">📊 Trading Signals</a>
      <a class="tab {{ 'active' if tab == 'news' else '' }}"
         href="/{{ date }}/news">📰 News Digest</a>
    </div>

    {% if content %}
      <div class="brief-content">{{ content|safe }}</div>
    {% else %}
      <div class="empty">
        <h2>Brief not found</h2>
        <p>No {{ tab }} brief for {{ formatted_date }}.</p>
      </div>
    {% endif %}
  {% endif %}
</div>

<footer>
  Daily Crypto Brief · Source: curated TG channels
</footer>

</body>
</html>"""


@app.route("/")
def index():
    all_dates = get_available_dates()
    return render_template_string(
        TEMPLATE,
        all_dates=all_dates,
        date=None,
        tab=None,
        content=None,
        formatted_date=None,
    )


@app.route("/<date_str>")
def date_redirect(date_str):
    return brief_view(date_str, "trading")


@app.route("/<date_str>/<tab>")
def brief_view(date_str, tab):
    all_dates = get_available_dates()
    if date_str not in all_dates:
        abort(404)

    brief_type = "trading_brief" if tab == "trading" else "news_digest"
    content = load_brief(date_str, brief_type)

    return render_template_string(
        TEMPLATE,
        all_dates=all_dates,
        date=date_str,
        tab=tab,
        content=content,
        formatted_date=format_date(date_str),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Trading Brief dashboard running on port {port}")
    app.run(debug=False, host="0.0.0.0", port=port)
