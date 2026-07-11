"""Build a static version of the Daily Crypto Brief dashboard into docs/ for GitHub Pages.

Each brief date gets two pages: {date}-trading.html and {date}-news.html.
index.html redirects to the newest trading page. All links are relative so the
site works under a subpath like chlocc.github.io/trading-agent/.
"""

import re
from datetime import datetime
from pathlib import Path

import markdown2

ROOT = Path(__file__).parent.parent
BRIEFS_DIR = ROOT / "data" / "briefs"
OUT_DIR = ROOT / "docs"

STYLE = """
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
      overflow-x: auto;
    }
    .nav-brand {
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      text-decoration: none;
      letter-spacing: -0.3px;
      white-space: nowrap;
    }
    .nav-brand span { color: var(--accent); }
    .date-nav { display: flex; gap: 8px; align-items: center; }
    .date-nav a {
      color: var(--muted);
      text-decoration: none;
      font-size: 13px;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--border);
      transition: all 0.15s;
      white-space: nowrap;
    }
    .date-nav a:hover, .date-nav a.active {
      color: var(--text);
      background: var(--border);
      border-color: var(--accent);
    }
    .container { max-width: 1100px; margin: 0 auto; padding: 40px 24px; }
    .disclaimer {
      font-size: 11px;
      color: var(--muted);
      text-align: center;
      margin-bottom: 16px;
      letter-spacing: 0.3px;
    }
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
    .tab.active { color: var(--text); border-bottom-color: var(--accent); }
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
    .brief-content p { margin-bottom: 12px; color: var(--text); }
    .brief-content ul, .brief-content ol { margin: 8px 0 16px 20px; }
    .brief-content li { margin-bottom: 8px; color: var(--text); }
    .brief-content strong { color: #fff; }
    .brief-content a { color: var(--blue); text-decoration: none; }
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
    .brief-content hr { border: none; border-top: 1px solid var(--border); margin: 32px 0; }
    .brief-content p:has(> strong:only-child) {
      background: var(--surface);
      padding: 10px 14px;
      border-radius: 8px;
      border-left: 3px solid var(--accent);
    }
    footer {
      text-align: center;
      padding: 32px;
      color: var(--muted);
      font-size: 13px;
      border-top: 1px solid var(--border);
      margin-top: 60px;
    }
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daily Crypto Brief — {formatted_date}</title>
  <style>{style}</style>
</head>
<body>

<nav>
  <a class="nav-brand" href="index.html"><span>◈</span> Daily Crypto Brief</a>
  <div class="date-nav">
{date_links}
  </div>
</nav>

<div class="container">
  <p class="disclaimer">Not investment advice. Not legal advice. Always do your own research.</p>
  <div class="tabs">
    <a class="tab {trading_active}" href="{date}-trading.html">📊 Trading Signals</a>
    <a class="tab {news_active}" href="{date}-news.html">📰 News Digest</a>
  </div>
  <div class="brief-content">{content}</div>
</div>

<footer>
  Daily Crypto Brief · Source: curated TG channels
</footer>

</body>
</html>"""


def linkify_tg(html: str) -> str:
    html = re.sub(
        r'\(→\s*(https://t\.me/[^\s\)]+)\)',
        r'<a href="\1" target="_blank" rel="noopener" class="tg-link">→ Telegram</a>',
        html,
    )
    html = re.sub(
        r'→\s*(https://t\.me/[^\s<\)]+)',
        r'<a href="\1" target="_blank" rel="noopener" class="tg-link">→ Telegram</a>',
        html,
    )
    return html


def render_markdown(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    content = re.sub(r"^---\n", "", content).strip()
    content = re.sub(r"\n---$", "", content).strip()
    html = markdown2.markdown(
        content,
        extras=["strike", "tables", "break-on-newline", "cuddled-lists"],
    )
    return linkify_tg(html)


def format_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y%m%d").strftime("%B %d, %Y")
    except ValueError:
        return date_str


def build():
    OUT_DIR.mkdir(exist_ok=True)

    dates = sorted(
        {
            m.group(1)
            for f in BRIEFS_DIR.glob("trading_brief_*.md")
            if (m := re.search(r"(\d{8})", f.name))
        },
        reverse=True,
    )
    if not dates:
        print("No briefs found — nothing to build.")
        return

    nav_dates = dates[:7]
    date_links = "\n".join(
        f'    <a href="{d}-trading.html" class="__ACTIVE_{d}__">'
        f"{d[4:6]}/{d[6:]}/{d[:4]}</a>"
        for d in nav_dates
    )

    pages_built = 0
    for date in dates:
        for tab, brief_type in (("trading", "trading_brief"), ("news", "news_digest")):
            src = BRIEFS_DIR / f"{brief_type}_{date}.md"
            if not src.exists():
                continue
            content = render_markdown(src)
            links = date_links.replace(f"__ACTIVE_{date}__", "active")
            links = re.sub(r"__ACTIVE_\d{8}__", "", links)
            html = PAGE.format(
                style=STYLE,
                formatted_date=format_date(date),
                date=date,
                date_links=links,
                trading_active="active" if tab == "trading" else "",
                news_active="active" if tab == "news" else "",
                content=content,
            )
            (OUT_DIR / f"{date}-{tab}.html").write_text(html, encoding="utf-8")
            pages_built += 1

    # index.html redirects to the newest trading brief
    latest = dates[0]
    (OUT_DIR / "index.html").write_text(
        f'<!DOCTYPE html><html><head><meta charset="UTF-8">'
        f'<meta http-equiv="refresh" content="0; url={latest}-trading.html">'
        f'<title>Daily Crypto Brief</title></head>'
        f'<body><a href="{latest}-trading.html">Latest brief</a></body></html>',
        encoding="utf-8",
    )
    # Tell GitHub Pages not to run Jekyll
    (OUT_DIR / ".nojekyll").write_text("")

    print(f"Built {pages_built} pages for {len(dates)} dates → {OUT_DIR}")
    print(f"Latest: {latest}-trading.html")


if __name__ == "__main__":
    build()
