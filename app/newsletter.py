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

def full_tweet_text(raw, stored_text=None):
  """Prefer note_tweet full text (long posts); otherwise stored/API text (often truncated)."""
  note = raw.get("note_tweet") or {}
  return note.get("text") or stored_text or raw.get("text") or ""

def _clean_source(raw):
  """Use note_tweet entities when cleaning full long-post text (indices match that text)."""
  note = raw.get("note_tweet") or {}
  if not note.get("text"): return raw
  entities = note.get("entities")
  if entities is None: return raw
  return {**raw, "entities": entities}

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

def _status_url(handle, tweet_id):
  if handle: return f"https://x.com/{handle}/status/{tweet_id}"
  return f"https://x.com/i/status/{tweet_id}"

def media_for_display(raw, status_url=None):
  """Shape stored API media objects for HTML/RSS rendering."""
  items = []; video_n = 0
  for m in raw.get("media_expanded") or []:
    url = _display_url(m)
    if not url: continue
    mtype = m.get("type")
    entry = {"type": mtype, "url": url, "alt": m.get("alt_text") or ""}
    if status_url and mtype in ("video", "animated_gif"):
      video_n += 1; entry["link_url"] = f"{status_url}/video/{video_n}"
    items.append(entry)
  return items

def quoted_for_display(raw):
  """Shape stored quoted_tweet blob for rendering, or None."""
  qt = raw.get("quoted_tweet")
  if not qt: return None
  handle = qt.get("author_handle"); tid = qt["id"]
  url = _status_url(handle, tid)
  src = _clean_source(qt)
  out = {
    "tweet_id": tid, "text": clean_tweet_text(full_tweet_text(qt), src),
    "url": url, "media": media_for_display(qt, url)}
  if handle: out["handle"] = handle
  return out

def order_entries_unread_first(items, read_ids):
  """Unread tweets first (chrono), then read tweets (chrono) at the bottom."""
  read_ids = set(read_ids or [])
  unread = [i for i in items if i.get("tweet_id") not in read_ids]
  read = [i for i in items if i.get("tweet_id") in read_ids]
  return unread + read

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
    status_url = f"https://x.com/{account['handle']}/status/{t['tweet_id']}"
    src = _clean_source(raw)
    item = {
      "tweet_id": t["tweet_id"], "kind": kind,
      "text": clean_tweet_text(full_tweet_text(raw, t.get("text")), src), "created_at": t["created_at"],
      "url": status_url,
      "likes": metrics.get("like_count", 0), "reposts": metrics.get("retweet_count", 0),
      "media": media_for_display(raw, status_url)}
    quoted = quoted_for_display(raw)
    if quoted: item["quoted"] = quoted
    items.append(item)
  items.sort(key=lambda i: i["created_at"])
  return items
