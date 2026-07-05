"""Digest builder: pure logic, no network or DB. Stored tweets + account settings -> digest items."""
import json

def build_digest(tweets, account):
  """Filter stored tweets by the account's settings and shape them for rendering.
  Settings also gate fetching, but filtering here too means a settings change
  re-shapes existing digests without refetching."""
  items = []
  for t in tweets:
    kind = t.get("kind", "post")
    if kind == "quote" and not account["include_quotes"]: continue
    if kind == "reply" and not account["include_replies"]: continue
    if kind == "retweet" and not account["include_retweets"]: continue
    raw = json.loads(t["raw_json"]) if isinstance(t.get("raw_json"), str) else t.get("raw_json", {})
    metrics = raw.get("public_metrics", {})
    items.append({
      "tweet_id": t["tweet_id"], "kind": kind, "text": t["text"], "created_at": t["created_at"],
      "url": f"https://x.com/{account['handle']}/status/{t['tweet_id']}",
      "likes": metrics.get("like_count", 0), "reposts": metrics.get("retweet_count", 0)})
  items.sort(key=lambda i: i["created_at"])
  return items
