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
  assert "isNewsletterBody(e.target)" in src
  assert "if (isNewsletterBody(e.target)) return;" in src
  assert "if (isNewsletterBody(e.target)) return;" in src.split("wheel")[1]

def test_carousel_js_drag_skips_newsletter_body():
  src = CAROUSEL_JS.read_text()
  mousedown = src.split("mousedown")[1].split("});")[0]
  assert "isNewsletterBody(e.target)" in mousedown

def test_carousel_js_arrow_keys():
  src = CAROUSEL_JS.read_text()
  assert "e.key === 'ArrowLeft'" in src
  assert "e.key === 'ArrowRight'" in src
  assert "e.key === 'ArrowUp'" in src
  assert "e.key === 'ArrowDown'" in src
  assert "scrollToCard(-1)" in src
  assert "scrollToCard(1)" in src
  assert "scrollActiveBodyBy" in src

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
