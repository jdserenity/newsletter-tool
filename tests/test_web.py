import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import create_app

@pytest.fixture
def client(tmp_path):
  app = create_app(db_path=str(tmp_path / "test.db"), with_scheduler=False)
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

def test_add_and_remove_account(client):
  r = client.post("/accounts", data={"handle": "@alice"}, follow_redirects=True)
  assert "@alice" in r.text
  assert "hello" not in r.text  # no edition yet
  c = db.connect(client.db_path)
  aid = db.get_account(c, handle="alice")["id"]
  r = client.post(f"/accounts/{aid}/remove", follow_redirects=True)
  assert "@alice" not in r.text

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
