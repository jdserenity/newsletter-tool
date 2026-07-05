"""RSS 2.0 generation from stored newsletter editions. Never touches the X API."""
import json
from xml.sax.saxutils import escape

def newsletter_feed(account, editions, base_url):
  """One feed per account; each weekly edition is one item linking to its web page."""
  items = []
  for e in editions:
    content = json.loads(e["content_json"])
    lines = [f"- {i['text']}" for i in content]
    desc = escape("\n".join(lines)) if lines else "No posts this week."
    title = escape(f"@{account['handle']} — week of {e['week_start'][:10]}")
    link = f"{base_url}/editions/{e['id']}"
    items.append(
      f"<item><title>{title}</title><link>{link}</link>"
      f"<guid isPermaLink=\"true\">{link}</guid>"
      f"<pubDate>{e['built_at']}</pubDate>"
      f"<description>{desc}</description></item>")
  name = escape(account.get("display_name") or account["handle"])
  return (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<rss version="2.0"><channel>'
    f"<title>Newsletter: {name}</title>"
    f"<link>{base_url}/</link>"
    f"<description>Weekly X newsletter for @{escape(account['handle'])}</description>"
    + "".join(items) + "</channel></rss>")
