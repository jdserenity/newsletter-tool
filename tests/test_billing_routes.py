import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.billing import BillingConfig
from app.main import create_app

class FakeStripeCheckout:
  @staticmethod
  def create(**kwargs):
    return {"id": "cs_test_entry", "url": "https://checkout.stripe.test/entry", "payment_status": "unpaid"}

  @staticmethod
  def retrieve(session_id, expand=None):
    return {
      "id": session_id, "payment_status": "paid", "status": "complete",
      "customer": "cus_test", "payment_intent": "pi_test",
      "amount_total": 100, "metadata": {"kind": "entry", "budget_credit_usd": "1"},
    }

class FakeStripe:
  checkout = type("checkout", (), {"Session": FakeStripeCheckout})()

@pytest.fixture
def billing_client(tmp_path, monkeypatch):
  monkeypatch.setenv("X_CLIENT_ID", "test-client-id")
  monkeypatch.setenv("X_CLIENT_SECRET", "test-client-secret")
  monkeypatch.setenv("X_OAUTH_CALLBACK_URL", "http://testserver/auth/callback")
  monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
  monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
  monkeypatch.setenv("APP_BASE_URL", "http://testserver")
  config = BillingConfig.from_env(enabled=True, stripe_module=FakeStripe)
  app = create_app(db_path=str(tmp_path / "bill.db"), with_scheduler=False,
    auth_enabled=True, billing_config=config)
  with TestClient(app) as c:
    yield c

def test_entry_checkout_redirects_to_stripe(billing_client):
  r = billing_client.get("/billing/checkout", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "https://checkout.stripe.test/entry"

def test_billing_success_unlocks_oauth(billing_client):
  r = billing_client.get("/billing/success?session_id=cs_test_entry", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/auth/login/start"
  r = billing_client.get("/auth/login/start", follow_redirects=False)
  assert r.status_code == 303
  assert "x.com/i/oauth2/authorize" in r.headers["location"]

def test_oauth_start_blocked_without_payment(billing_client):
  r = billing_client.get("/auth/login/start", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/billing/checkout"

def test_returning_login_skips_entry_payment(billing_client):
  r = billing_client.get("/auth/login/start?returning=1", follow_redirects=False)
  assert r.status_code == 303
  assert "x.com/i/oauth2/authorize" in r.headers["location"]

def test_oauth_callback_links_entry_payment(billing_client, monkeypatch):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "99", "username": "owner", "name": "Owner"})
  billing_client.get("/billing/success?session_id=cs_test_entry", follow_redirects=False)
  login = billing_client.get("/auth/login/start", follow_redirects=False)
  state = login.headers["location"].split("state=")[1].split("&")[0]
  # state from URL - need proper parse
  from urllib.parse import parse_qs, urlparse
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  r = billing_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
  assert r.status_code == 303
  c = db.connect(billing_client.app.state.db_path)
  row = db.get_billing_account(c, x_user_id="99")
  assert row is not None
  assert row["budget_usd"] == pytest.approx(1.0)
