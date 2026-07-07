import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import create_app

@pytest.fixture
def client(tmp_path):
  app = create_app(db_path=str(tmp_path / "test.db"), with_scheduler=False, auth_enabled=False)
  with TestClient(app) as c:
    c.db_path = str(tmp_path / "test.db")
    yield c

def test_home_empty(client):
  r = client.get("/")
  assert r.status_code == 200
  assert "Newsletter Tool" in r.text
  assert "Add account" in r.text
  assert "digest" not in r.text.lower()
  assert "tracked account" not in r.text.lower()
  assert "log off without losing the signal" in r.text
  assert 'class="site-brand"' in r.text
  assert "min-height:" in r.text and "newsletter-card" in r.text
  assert "flex-wrap: nowrap" in r.text and "newsletter-toolbar" in r.text
  assert "justify-content: space-between" in r.text
  assert "flex-direction: column" in r.text and "newsletter-identity" in r.text

def test_add_account(client):
  r = client.post("/accounts", data={"handle": "@alice"}, follow_redirects=True)
  assert r.status_code == 200
  assert 'href="https://x.com/alice"' in r.text
  assert "hello" not in r.text  # no edition yet

def test_remove_account_via_api(client):
  client.post("/accounts", data={"handle": "@alice"})
  c = db.connect(client.db_path)
  aid = db.get_account(c, handle="alice")["id"]
  r = client.post(f"/accounts/{aid}/remove", follow_redirects=True)
  assert "@alice" not in r.text
  assert "/settings" in str(r.request.url)

def test_settings_page_lists_accounts_and_remove(client):
  client.post("/accounts", data={"handle": "@alice"})
  client.post("/accounts", data={"handle": "bob"})
  r = client.get("/settings")
  assert r.status_code == 200
  assert "Settings" in r.text
  assert "@alice" in r.text
  assert "@bob" in r.text
  assert r.text.count("/remove") == 2
  c = db.connect(client.db_path)
  aid = db.get_account(c, handle="alice")["id"]
  r = client.post(f"/accounts/{aid}/remove", follow_redirects=True)
  assert "@alice" not in r.text
  assert "@bob" in r.text

def test_settings_page_empty(client):
  r = client.get("/settings")
  assert r.status_code == 200
  assert "No tracked accounts yet" in r.text

def test_home_multiple_accounts_shows_carousel_and_add_card(client):
  client.post("/accounts", data={"handle": "alice"})
  client.post("/accounts", data={"handle": "bob"})
  r = client.get("/")
  assert r.text.count('href="https://x.com/') == 2
  assert 'class="newsletter-card add-card"' in r.text
  assert 'id="newsletter-carousel"' in r.text
  assert "overflow-x: auto" in r.text

def test_home_has_no_remove_button(client):
  client.post("/accounts", data={"handle": "alice"})
  r = client.get("/")
  assert "/remove" not in r.text

def test_rss_link_has_icon(client):
  client.post("/accounts", data={"handle": "alice"})
  r = client.get("/")
  assert 'class="rss-link"' in r.text
  assert "<svg" in r.text

def test_settings_roundtrip(client):
  client.post("/accounts", data={"handle": "alice"})
  c = db.connect(client.db_path)
  aid = db.get_account(c, handle="alice")["id"]
  client.post(f"/accounts/{aid}/settings", data={"include_retweets": "true"})  # quotes unchecked -> off
  a = db.get_account(db.connect(client.db_path), account_id=aid)
  assert a["include_quotes"] == 0; assert a["include_retweets"] == 1

def _seed_edition(db_path):
  c = db.connect(db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "1", "kind": "post", "text": "hello world", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/1", "likes": 3, "reposts": 1}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.02)
  return aid

def test_home_shows_newsletter_inline(client):
  _seed_edition(client.db_path)
  r = client.get("/")
  assert r.status_code == 200
  assert "hello world" in r.text
  assert "$0.02" in r.text
  assert "newsletter-card" in r.text

def test_edition_page_renders(client):
  _seed_edition(client.db_path)
  c = db.connect(client.db_path)
  eid = db.list_editions(c)[0]["id"]
  r = client.get(f"/editions/{eid}")
  assert r.status_code == 200
  assert "hello world" in r.text; assert "$0.020" in r.text

def test_edition_page_renders_media(client):
  c = db.connect(client.db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "1", "kind": "post", "text": "sunset pic", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/1", "likes": 3, "reposts": 1,
            "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/x.jpg?name=medium", "alt": "sky"}]}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.02)
  eid = db.list_editions(c)[0]["id"]
  r = client.get(f"/editions/{eid}")
  assert 'class="tweet-media"' in r.text
  assert 'src="https://pbs.twimg.com/media/x.jpg?name=medium"' in r.text
  assert 'alt="sky"' in r.text

def test_edition_page_renders_quoted_media(client):
  c = db.connect(client.db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "2", "kind": "quote", "text": "my take", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/2", "likes": 1, "reposts": 0,
            "quoted": {"tweet_id": "999", "handle": "bob", "text": "bob pic", "url": "https://x.com/bob/status/999",
                       "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/q.jpg?name=medium", "alt": ""}]}}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.02)
  eid = db.list_editions(c)[0]["id"]
  r = client.get(f"/editions/{eid}")
  assert 'class="quoted-tweet"' in r.text
  assert "@bob" in r.text
  assert "bob pic" in r.text
  assert 'src="https://pbs.twimg.com/media/q.jpg?name=medium"' in r.text

def test_edition_page_video_has_play_button(client):
  c = db.connect(client.db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "1", "kind": "post", "text": "watch this", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/1", "likes": 1, "reposts": 0,
            "media": [{"type": "video", "url": "https://pbs.twimg.com/thumb.jpg", "alt": "",
                       "link_url": "https://x.com/alice/status/1/video/1"}]}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.02)
  eid = db.list_editions(c)[0]["id"]
  r = client.get(f"/editions/{eid}")
  assert "media-thumb-video" in r.text
  assert 'href="https://x.com/alice/status/1/video/1"' in r.text

def test_rss_feed(client):
  aid = _seed_edition(client.db_path)
  r = client.get(f"/feeds/{aid}.xml")
  assert r.status_code == 200
  assert r.headers["content-type"].startswith("application/rss+xml")
  assert "<rss" in r.text; assert "hello world" in r.text
  assert "week of 2026-06-29" in r.text
  assert "digest" not in r.text.lower()

def test_missing_pages_404(client):
  assert client.get("/editions/999").status_code == 404
  assert client.get("/accounts/999").status_code == 404
  assert client.get("/feeds/999.xml").status_code == 404

def test_account_page_redirects_home(client):
  aid = _seed_edition(client.db_path)
  r = client.get(f"/accounts/{aid}", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/"
