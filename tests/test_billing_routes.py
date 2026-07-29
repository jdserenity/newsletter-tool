import pytest
from urllib.parse import parse_qs, urlparse

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

def _oauth_login(client, monkeypatch, x_user_id="99", username="owner"):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {
    "id": x_user_id, "username": username, "name": "Owner"})
  login = client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  return client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)

def test_entry_checkout_redirects_to_stripe(billing_client):
  r = billing_client.get("/billing/checkout", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "https://checkout.stripe.test/entry"

def test_oauth_start_always_goes_to_x(billing_client):
  r = billing_client.get("/auth/login/start", follow_redirects=False)
  assert r.status_code == 303
  assert "x.com/i/oauth2/authorize" in r.headers["location"]

def test_oauth_callback_unpaid_goes_to_checkout(billing_client, monkeypatch):
  r = _oauth_login(billing_client, monkeypatch)
  assert r.status_code == 303
  assert r.headers["location"] == "/billing/checkout"
  # Session is stored so checkout success can link payment without re-OAuth.
  assert billing_client.cookies.get("session") is not None

def test_billing_success_links_payment_when_signed_in(billing_client, monkeypatch):
  r = _oauth_login(billing_client, monkeypatch)
  assert r.headers["location"] == "/billing/checkout"
  r = billing_client.get("/billing/success?session_id=cs_test_entry", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/"
  c = db.connect(billing_client.app.state.db_path)
  row = db.get_billing_account(c, x_user_id="99")
  assert row is not None
  assert row["budget_usd"] == pytest.approx(1.0)

def test_billing_success_unsigned_sends_to_oauth(billing_client):
  r = billing_client.get("/billing/success?session_id=cs_test_entry", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/auth/login/start"

def test_oauth_callback_links_pending_entry_payment(billing_client, monkeypatch):
  # Pay while signed out, then OAuth — callback attaches the pending Checkout session.
  billing_client.get("/billing/success?session_id=cs_test_entry", follow_redirects=False)
  r = _oauth_login(billing_client, monkeypatch)
  assert r.status_code == 303
  assert r.headers["location"] == "/"
  c = db.connect(billing_client.app.state.db_path)
  row = db.get_billing_account(c, x_user_id="99")
  assert row is not None
  assert row["budget_usd"] == pytest.approx(1.0)

def test_landing_enter_goes_to_oauth_not_checkout(billing_client):
  r = billing_client.get("/", follow_redirects=False)
  assert r.status_code == 200
  assert 'href="/auth/login/start"' in r.text
  assert "/billing/checkout" not in r.text
  assert "Already in?" not in r.text
  assert "returning=1" not in r.text
