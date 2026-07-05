import json
from app.newsletter import build_newsletter, clean_tweet_text, media_for_display, quoted_for_display
from tests.conftest import make_tweet

ACCOUNT = {"handle": "alice", "include_quotes": 1, "include_replies": 0, "include_retweets": 0}

PHOTO_RAW = {
  "id": "99", "text": "sunset pic https://t.co/abc123", "created_at": "2026-06-30T12:00:00Z",
  "public_metrics": {"like_count": 3, "retweet_count": 1},
  "attachments": {"media_keys": ["3_99"]},
  "entities": {"urls": [{"start": 11, "end": 33, "url": "https://t.co/abc123", "expanded_url": "https://pic.twitter.com/xyz", "media_key": "3_99"}]},
  "media_expanded": [{"media_key": "3_99", "type": "photo", "url": "https://pbs.twimg.com/media/AbCd.jpg", "alt_text": "orange sky"}],
}

def test_includes_posts_and_quotes_by_default():
  tweets = [make_tweet("1", "post"), make_tweet("2", "quote")]
  items = build_newsletter(tweets, ACCOUNT)
  assert [i["tweet_id"] for i in items] == ["1", "2"]

def test_excludes_quotes_when_setting_off():
  tweets = [make_tweet("1", "post"), make_tweet("2", "quote")]
  items = build_newsletter(tweets, {**ACCOUNT, "include_quotes": 0})
  assert [i["tweet_id"] for i in items] == ["1"]

def test_excludes_replies_and_retweets_by_default():
  tweets = [make_tweet("1", "reply"), make_tweet("2", "retweet"), make_tweet("3", "post")]
  items = build_newsletter(tweets, ACCOUNT)
  assert [i["tweet_id"] for i in items] == ["3"]

def test_items_sorted_chronologically():
  tweets = [make_tweet("2", created_at="2026-07-02T09:00:00Z"), make_tweet("1", created_at="2026-07-01T09:00:00Z")]
  items = build_newsletter(tweets, ACCOUNT)
  assert [i["tweet_id"] for i in items] == ["1", "2"]

def test_item_shape():
  items = build_newsletter([make_tweet("42", metrics={"like_count": 7, "retweet_count": 2})], ACCOUNT)
  item = items[0]
  assert item["url"] == "https://x.com/alice/status/42"
  assert item["likes"] == 7; assert item["reposts"] == 2; assert item["kind"] == "post"
  assert item["media"] == []

def test_clean_tweet_text_strips_media_tco():
  assert clean_tweet_text(PHOTO_RAW["text"], PHOTO_RAW) == "sunset pic"

def test_media_for_display_photo_adds_size_suffix():
  items = media_for_display(PHOTO_RAW)
  assert len(items) == 1
  assert items[0]["type"] == "photo"
  assert items[0]["url"] == "https://pbs.twimg.com/media/AbCd.jpg?name=medium"
  assert items[0]["alt"] == "orange sky"

def test_media_for_display_video_uses_preview():
  raw = {"media_expanded": [{"type": "video", "preview_image_url": "https://pbs.twimg.com/thumb.jpg"}]}
  items = media_for_display(raw)
  assert items[0]["url"] == "https://pbs.twimg.com/thumb.jpg"

def test_build_newsletter_includes_media_and_strips_tco():
  tweet = {"tweet_id": "99", "kind": "post", "text": PHOTO_RAW["text"], "created_at": PHOTO_RAW["created_at"],
           "raw_json": json.dumps(PHOTO_RAW)}
  items = build_newsletter([tweet], ACCOUNT)
  assert items[0]["text"] == "sunset pic"
  assert len(items[0]["media"]) == 1
  assert "t.co" not in items[0]["text"]

QUOTE_RAW = {
  "id": "2", "text": "my take", "created_at": "2026-07-01T10:00:00Z",
  "public_metrics": {"like_count": 1, "retweet_count": 0},
  "referenced_tweets": [{"type": "quoted", "id": "999"}],
  "quoted_tweet": {
    "id": "999", "text": "bob pic https://t.co/qpic",
    "entities": {"urls": [{"start": 8, "end": 28, "url": "https://t.co/qpic", "media_key": "3_999",
                           "expanded_url": "https://pic.twitter.com/q"}]},
    "attachments": {"media_keys": ["3_999"]},
    "media_expanded": [{"media_key": "3_999", "type": "photo", "url": "https://pbs.twimg.com/media/q.jpg"}],
  },
}

def test_quoted_for_display_strips_tco_and_includes_media():
  q = quoted_for_display(QUOTE_RAW)
  assert q["text"] == "bob pic"
  assert q["url"] == "https://x.com/i/status/999"
  assert len(q["media"]) == 1

def test_build_newsletter_includes_quoted_block():
  tweet = {"tweet_id": "2", "kind": "quote", "text": "my take", "created_at": QUOTE_RAW["created_at"],
           "raw_json": json.dumps(QUOTE_RAW)}
  items = build_newsletter([tweet], ACCOUNT)
  assert items[0]["quoted"]["text"] == "bob pic"
  assert len(items[0]["quoted"]["media"]) == 1
