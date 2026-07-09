"""RSS 2.0 generation from stored newsletter editions. Never touches the X API."""
import json
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

def _media_html(media):
  parts = []
  for m in media or []:
    url = escape(m.get("url") or ""); alt = escape(m.get("alt") or "")
    if url: parts.append(f'<br><img src="{url}" alt="{alt}">')
  return "".join(parts)

def item_description_html(item):
  """Build escaped HTML description for one newsletter item, including inline media."""
  parts = [escape(item.get("text") or ""), _media_html(item.get("media"))]
  q = item.get("quoted")
  if q:
    who = f"@{q['handle']}: " if q.get("handle") else ""
    parts.append(f'<br><blockquote>{escape(who + (q.get("text") or ""))}</blockquote>')
    parts.append(_media_html(q.get("media")))
  return "".join(parts)

def rfc822_pub_date(value):
  """RSS <pubDate> must be RFC 822 (e.g. Mon, 30 Jun 2026 12:00:00 +0000), not SQLite timestamps."""
  if not value:
    return format_datetime(datetime.now(timezone.utc))
  s = str(value).strip().replace("T", " ").replace("Z", "")
  for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M:%S.%f", 26)):
    try:
      dt = datetime.strptime(s[:n], fmt).replace(tzinfo=timezone.utc)
      return format_datetime(dt)
    except ValueError:
      continue
  return format_datetime(datetime.now(timezone.utc))

def newsletter_feed(account, editions, base_url):
  """One feed per account; each weekly edition is one item linking to its web page."""
  items = []
  for e in editions:
    content = json.loads(e["content_json"])
    blocks = [item_description_html(i) for i in content]
    desc = "<br><br>".join(blocks) if blocks else escape("No posts this week.")
    title = escape(f"@{account['handle']} — week of {e['week_start'][:10]}")
    link = f"{base_url}/editions/{e['id']}"
    items.append(
      f"<item><title>{title}</title><link>{link}</link>"
      f"<guid isPermaLink=\"true\">{link}</guid>"
      f"<pubDate>{rfc822_pub_date(e.get('built_at'))}</pubDate>"
      f"<description>{desc}</description></item>")
  name = escape(account.get("display_name") or account["handle"])
  feed_url = f"{base_url}/feeds/{account['id']}.xml"
  return (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
    f"<title>Mentally Stable X Experience: {name}</title>"
    f"<link>{base_url}/</link>"
    f'<atom:link href="{escape(feed_url)}" rel="self" type="application/rss+xml"/>'
    f"<description>Weekly X newsletter for @{escape(account['handle'])}</description>"
    + "".join(items) + "</channel></rss>")
