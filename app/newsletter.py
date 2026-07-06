"""Newsletter builder: pure logic, no network or DB. Stored tweets + account settings -> newsletter items."""
import json
import re

def _quoted_id(raw):
  if raw.get("quoted_tweet", {}).get("id"): return raw["quoted_tweet"]["id"]
  return next((r["id"] for r in (raw.get("referenced_tweets") or []) if r.get("type") == "quoted"), None)

def _is_media_tco(url_entity, raw):
  """True when a t.co entry in entities points at attached tweet media."""
  if url_entity.get("media_key"): return True
  exp = url_entity.get("expanded_url") or ""
  if "pic.twitter.com" in exp or "/photo/" in exp or "/video/" in exp: return True
  keys = set(_media_keys(raw))
  return bool(url_entity.get("media_key") in keys)

def _media_keys(raw):
  keys = list((raw.get("attachments") or {}).get("media_keys") or [])
  for u in (raw.get("entities") or {}).get("urls") or []:
    mk = u.get("media_key")
    if mk and mk not in keys: keys.append(mk)
  return keys

def _is_quote_tco(url_entity, raw):
  """True when a t.co entry points at the quoted tweet we render inline."""
  qid = _quoted_id(raw)
  if not qid: return False
  exp = url_entity.get("expanded_url") or ""
  return qid in exp

def clean_tweet_text(text, raw):
  """Remove t.co short links replaced by inline media or quoted blocks."""
  entities = raw.get("entities") or {}
  spans = [u for u in entities.get("urls") or []
           if ("start" in u and "end" in u) and (_is_media_tco(u, raw) or _is_quote_tco(u, raw))]
  out = text
  for u in sorted(spans, key=lambda x: x["start"], reverse=True):
    out = out[:u["start"]] + out[u["end"]:]
  if ((_media_keys(raw) and (raw.get("media_expanded") or [])) or _quoted_id(raw)) and "t.co/" in out:
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

def quoted_for_display(raw):
  """Shape stored quoted_tweet blob for rendering, or None."""
  qt = raw.get("quoted_tweet")
  if not qt: return None
  handle = qt.get("author_handle")
  tid = qt["id"]
  url = f"https://x.com/{handle}/status/{tid}" if handle else f"https://x.com/i/status/{tid}"
  out = {
    "tweet_id": tid, "text": clean_tweet_text(qt.get("text") or "", qt),
    "url": url, "media": media_for_display(qt)}
  if handle: out["handle"] = handle
  return out

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
    item = {
      "tweet_id": t["tweet_id"], "kind": kind,
      "text": clean_tweet_text(t["text"], raw), "created_at": t["created_at"],
      "url": f"https://x.com/{account['handle']}/status/{t['tweet_id']}",
      "likes": metrics.get("like_count", 0), "reposts": metrics.get("retweet_count", 0),
      "media": media_for_display(raw)}
    quoted = quoted_for_display(raw)
    if quoted: item["quoted"] = quoted
    items.append(item)
  items.sort(key=lambda i: i["created_at"])
  return items
