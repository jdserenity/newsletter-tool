from app.digest import build_digest
from tests.conftest import make_tweet

ACCOUNT = {"handle": "alice", "include_quotes": 1, "include_replies": 0, "include_retweets": 0}

def test_includes_posts_and_quotes_by_default():
  tweets = [make_tweet("1", "post"), make_tweet("2", "quote")]
  items = build_digest(tweets, ACCOUNT)
  assert [i["tweet_id"] for i in items] == ["1", "2"]

def test_excludes_quotes_when_setting_off():
  tweets = [make_tweet("1", "post"), make_tweet("2", "quote")]
  items = build_digest(tweets, {**ACCOUNT, "include_quotes": 0})
  assert [i["tweet_id"] for i in items] == ["1"]

def test_excludes_replies_and_retweets_by_default():
  tweets = [make_tweet("1", "reply"), make_tweet("2", "retweet"), make_tweet("3", "post")]
  items = build_digest(tweets, ACCOUNT)
  assert [i["tweet_id"] for i in items] == ["3"]

def test_items_sorted_chronologically():
  tweets = [make_tweet("2", created_at="2026-07-02T09:00:00Z"), make_tweet("1", created_at="2026-07-01T09:00:00Z")]
  items = build_digest(tweets, ACCOUNT)
  assert [i["tweet_id"] for i in items] == ["1", "2"]

def test_item_shape():
  items = build_digest([make_tweet("42", metrics={"like_count": 7, "retweet_count": 2})], ACCOUNT)
  item = items[0]
  assert item["url"] == "https://x.com/alice/status/42"
  assert item["likes"] == 7; assert item["reposts"] == 2; assert item["kind"] == "post"
