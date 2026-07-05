"""Newsletter builder: pure logic, no network or DB. Stored tweets + account settings -> newsletter items."""
import json
import re

def _is_media_tco(url_entity, raw):
  """True when a t.co entry in entities points at attached tweet media."""
  if url_entity.get("media_key"): return True
  exp = url_entity.get("expanded_url") or ""
  if "pic.twitter.com" in exp or "/photo/" in exp: return True
  keys = set((raw.get("attachments") or {}).get("media_keys") or [])
  return bool(url_entity.get("media_key") in keys)

def clean_tweet_text(text, raw):
  """Remove t.co short links that point at inline media we render separately."""
  entities = raw.get("entities") or {}
  spans = [u for u in entities.get("urls") or [] if _is_media_tco(u, raw) and "start" in u and "end" in u]
  out = text
  for u in sorted(spans, key=lambda x: x["start"], reverse=True):
    out = out[:u["start"]] + out[u["end"]:]
  if (raw.get("media_expanded") or []) and "t.co/" in out:
    out = re.sub(r"\s*https://t\.co/\w+\s*$", "", out)
  return re.sub(r"  +", " ", out).strip()

def _display_url(m):
  mtype = m.get("type")
  if mtype == "photo":
    url = m.get("url") or ""
    if not url: return ""
    if "name=" in url: return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}name=medium"
  return m.get("preview_image_url") or m.get("url") or ""

def media_for_display(raw):
  """Shape stored API media objects for HTML/RSS rendering."""
  items = []
  for m in raw.get("media_expanded") or []:
    url = _display_url(m)
    if not url: continue
    items.append({"type": m.get("type"), "url": url, "alt": m.get("alt_text") or ""})
  return items

def build_newsletter(tweets, account):
  """Filter stored tweets by the account's settings and shape them for rendering.
  Settings also gate fetching, but filtering here too means a settings change
  re-shapes existing newsletters without refetching."""
  items = []
  for t in tweets:
    kind = t.get("kind", "post")
    if kind == "quote" and not account["include_quotes"]: continue
    if kind == "reply" and not account["include_replies"]: continue
    if kind == "retweet" and not account["include_retweets"]: continue
    raw = json.loads(t["raw_json"]) if isinstance(t.get("raw_json"), str) else t.get("raw_json", {})
    metrics = raw.get("public_metrics", {})
    items.append({
      "tweet_id": t["tweet_id"], "kind": kind,
      "text": clean_tweet_text(t["text"], raw), "created_at": t["created_at"],
      "url": f"https://x.com/{account['handle']}/status/{t['tweet_id']}",
      "likes": metrics.get("like_count", 0), "reposts": metrics.get("retweet_count", 0),
      "media": media_for_display(raw)})
  items.sort(key=lambda i: i["created_at"])
  return items
