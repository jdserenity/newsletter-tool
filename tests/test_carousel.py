from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

CAROUSEL_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "carousel.js"

@pytest.fixture
def client(tmp_path):
  app = create_app(db_path=str(tmp_path / "test.db"), with_scheduler=False, auth_enabled=False)
  with TestClient(app) as c:
    c.db_path = str(tmp_path / "test.db")
    yield c

def test_carousel_js_spatial_wheel_zones():
  src = CAROUSEL_JS.read_text()
  # wheel listener is on document, bails out only for newsletter-body
  assert "document.addEventListener('wheel'" in src
  assert "if (isNewsletterBody(e.target)) return;" in src

def test_carousel_js_drag_skips_selectable_text_not_whole_body():
  src = CAROUSEL_JS.read_text()
  mousedown_block = src.split("mousedown")[1].split("});")[0]
  # drag should bail on selectable text, not the whole newsletter body
  assert "isSelectableText(e.target)" in mousedown_block
  # newsletter body as a whole should NOT block drag anymore
  assert "isNewsletterBody(e.target)" not in mousedown_block

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
  # scrollToCard uses allCards() which includes .add-card
  assert "function allCards()" in src
  assert "scrollToCard" in src
  # allCards does NOT exclude add-card
  allcards_fn = src.split("function allCards()")[1].split("}")[0]
  assert "add-card" not in allcards_fn

def test_carousel_js_no_page_scroll():
  # body and html must be overflow: hidden so page cannot scroll
  css = Path(__file__).resolve().parents[1] / "app" / "templates" / "base.html"
  src = css.read_text()
  assert "html, body { overflow: hidden" in src

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

def test_cursor_auto_on_tweet_text(client):
  r = client.get("/")
  assert "cursor: auto" in r.text
  assert ".tweet-text, .week-label { cursor: text" not in r.text
