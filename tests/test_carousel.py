from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

CAROUSEL_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "carousel.js"
BASE_HTML = Path(__file__).resolve().parents[1] / "app" / "templates" / "base.html"
MACROS_HTML = Path(__file__).resolve().parents[1] / "app" / "templates" / "_tweet_macros.html"

@pytest.fixture
def client(tmp_path):
  app = create_app(db_path=str(tmp_path / "test.db"), with_scheduler=False, auth_enabled=False)
  with TestClient(app) as c:
    c.db_path = str(tmp_path / "test.db")
    yield c

def test_carousel_js_wheel_on_document():
  src = CAROUSEL_JS.read_text()
  assert "document.addEventListener('wheel'" in src

def test_carousel_js_wheel_never_chains_at_scroll_edges():
  src = CAROUSEL_JS.read_text()
  # once a body has any overflow, wheel always scrolls it (even at top/bottom) —
  # no edge-triggered handoff into the horizontal carousel
  assert "bodyHasOverflow" in src
  assert "if (bodyHasOverflow(body)) return;" in src
  # must not key the decision off scrollTop/direction anymore (old edge-chaining logic)
  assert "body.scrollTop > 0" not in src
  assert "body.scrollTop < body.scrollHeight" not in src

def test_carousel_js_direction_aware_drag():
  src = CAROUSEL_JS.read_text()
  assert "dragMode" in src
  assert "'vertical'" in src
  assert "'horizontal'" in src
  assert "dragBody.scrollTop = startScrollTop - dy" in src
  assert "carousel.scrollLeft = scrollLeft - dx" in src

def test_carousel_js_drag_allowed_from_newsletter_body_but_not_text():
  src = CAROUSEL_JS.read_text()
  mousedown_block = src.split("mousedown")[1].split("});")[0]
  # dragging must bail only on actual text content, not the whole newsletter-body zone
  assert "isSelectableText(e.target)" in mousedown_block
  assert "if (isNewsletterBody(e.target)) return;" not in src

def test_carousel_js_selectable_text_targets_text_content_span():
  src = CAROUSEL_JS.read_text()
  # narrow selector — only the inline text span, not the whole tweet-text block —
  # so the surrounding empty space in that block still starts a drag
  assert "isSelectableText(el) { return el && el.closest && el.closest('.text-content'); }" in src

def test_carousel_js_arrow_keys():
  src = CAROUSEL_JS.read_text()
  assert "e.key === 'ArrowLeft'" in src
  assert "e.key === 'ArrowRight'" in src
  assert "e.key === 'ArrowUp'" in src
  assert "e.key === 'ArrowDown'" in src
  assert "scrollToCard(-1)" in src
  assert "scrollToCard(1)" in src
  assert "scrollActiveBodyBy" in src

def test_carousel_js_arrows_include_add_card():
  src = CAROUSEL_JS.read_text()
  assert "function allCards()" in src
  allcards_fn = src.split("function allCards()")[1].split("}")[0]
  assert "add-card" not in allcards_fn

def test_carousel_js_no_page_scroll():
  assert "html, body { overflow: hidden" in BASE_HTML.read_text()

def test_carousel_js_ignores_arrow_keys_in_form_fields():
  assert "isFormField(e.target)" in CAROUSEL_JS.read_text()

def test_home_loads_carousel_script(client):
  r = client.get("/")
  assert r.status_code == 200
  assert 'src="/static/carousel.js"' in r.text

def test_carousel_js_served(tmp_path):
  app = create_app(db_path=str(tmp_path / "test.db"), with_scheduler=False, auth_enabled=False)
  with TestClient(app) as c:
    r = c.get("/static/carousel.js")
  assert r.status_code == 200
  assert "newsletter-carousel" in r.text

def test_newsletter_body_hides_scrollbar(client):
  r = client.get("/")
  assert ".newsletter-body::-webkit-scrollbar { display: none; }" in r.text
  assert "scrollbar-width: none" in r.text

def test_tweet_text_block_has_no_explicit_cursor(client):
  r = client.get("/")
  # the block-level wrapper (.tweet-text/.week-label) must not set cursor itself —
  # that's what made the text cursor appear over empty space far from the text
  assert ".tweet-text, .week-label { cursor:" not in r.text

def test_text_content_span_has_text_cursor(client):
  r = client.get("/")
  assert ".text-content { cursor: text;" in r.text

def test_tweet_text_wraps_content_in_text_content_span(client):
  from app import db
  c = db.connect(client.db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "1", "kind": "post", "text": "hello world", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/1", "likes": 0, "reposts": 0}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.0)
  r = client.get("/")
  assert '<span class="text-content">hello world</span>' in r.text
  assert 'class="tweet-more"' in r.text

def test_images_are_not_natively_draggable(client):
  from app import db
  c = db.connect(client.db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "1", "kind": "post", "text": "pic", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/1", "likes": 0, "reposts": 0,
            "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/x.jpg", "alt": ""}]}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.0)
  r = client.get("/")
  assert 'draggable="false"' in r.text
  assert "-webkit-user-drag: none" in r.text

def test_newsletter_body_contains_overscroll(client):
  r = client.get("/")
  assert "overscroll-behavior: contain" in r.text

def test_photo_renders_as_div_not_link():
  src = MACROS_HTML.read_text()
  # photos must use div.media-thumb, not an anchor
  assert "<div class=\"media-thumb\">" in src

def test_video_still_renders_as_link():
  src = MACROS_HTML.read_text()
  assert "media-thumb-video" in src
  assert 'href="{{ m.link_url or link_url }}"' in src

def test_edition_page_photo_has_no_link(client):
  from app import db
  c = db.connect(client.db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "1", "kind": "post", "text": "nice pic", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/1", "likes": 1, "reposts": 0,
            "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/x.jpg?name=medium", "alt": ""}]}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.01)
  eid = db.list_editions(c)[0]["id"]
  r = client.get(f"/editions/{eid}")
  assert 'class="media-thumb"' in r.text
  # photo div must not be wrapped in an anchor pointing to X
  assert 'class="media-thumb media-thumb-video"' not in r.text
  assert '<a href="https://x.com/alice/status/1" class="media-thumb"' not in r.text

def test_edition_page_video_still_links(client):
  from app import db
  c = db.connect(client.db_path)
  aid = db.add_account(c, "alice")
  items = [{"tweet_id": "1", "kind": "post", "text": "watch", "created_at": "2026-06-30T10:00:00Z",
            "url": "https://x.com/alice/status/1", "likes": 1, "reposts": 0,
            "media": [{"type": "video", "url": "https://pbs.twimg.com/thumb.jpg", "alt": "",
                       "link_url": "https://x.com/alice/status/1/video/1"}]}]
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", items, 0.01)
  eid = db.list_editions(c)[0]["id"]
  r = client.get(f"/editions/{eid}")
  assert 'class="media-thumb media-thumb-video"' in r.text
  assert 'href="https://x.com/alice/status/1/video/1"' in r.text
