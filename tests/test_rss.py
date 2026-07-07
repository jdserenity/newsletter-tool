import json
from app import db
from app.rss import item_description_html, newsletter_feed

def test_item_description_html_includes_image(conn):
  item = {"text": "sunset pic", "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/x.jpg?name=medium", "alt": "sky"}]}
  html = item_description_html(item)
  assert "sunset pic" in html
  assert '<img src="https://pbs.twimg.com/media/x.jpg?name=medium"' in html
  assert 'alt="sky"' in html

def test_item_description_html_includes_quoted_media(conn):
  item = {"text": "my take", "quoted": {"handle": "bob", "text": "bob pic", "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/q.jpg", "alt": ""}]}}
  html = item_description_html(item)
  assert "my take" in html; assert "@bob:" in html; assert "bob pic" in html
  assert "pbs.twimg.com/media/q.jpg" in html

def test_newsletter_feed_description_has_images(conn):
  aid = db.add_account(conn, "alice")
  items = [{"text": "pic", "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/x.jpg", "alt": ""}]}]
  db.save_edition(conn, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.01)
  feed = newsletter_feed(db.get_account(conn, account_id=aid), db.list_editions(conn, aid), "http://test")
  assert "pbs.twimg.com/media/x.jpg" in feed
