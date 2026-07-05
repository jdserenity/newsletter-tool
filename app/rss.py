"""RSS 2.0 generation from stored digests. Never touches the X API."""
import json
from xml.sax.saxutils import escape

def digest_feed(account, digests, base_url):
  """One feed per account; each digest is one item linking to its web page."""
  items = []
  for d in digests:
    content = json.loads(d["content_json"])
    lines = [f"- {i['text']}" for i in content]
    desc = escape("\n".join(lines)) if lines else "No posts this week."
    title = escape(f"@{account['handle']} digest: week of {d['week_start'][:10]}")
    link = f"{base_url}/digests/{d['id']}"
    items.append(
      f"<item><title>{title}</title><link>{link}</link>"
      f"<guid isPermaLink=\"true\">{link}</guid>"
      f"<pubDate>{d['built_at']}</pubDate>"
      f"<description>{desc}</description></item>")
  name = escape(account.get("display_name") or account["handle"])
  return (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<rss version="2.0"><channel>'
    f"<title>Weekly digest: {name}</title>"
    f"<link>{base_url}/accounts/{account['id']}</link>"
    f"<description>Weekly X digest for @{escape(account['handle'])}</description>"
    + "".join(items) + "</channel></rss>")
