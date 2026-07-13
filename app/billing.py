"""Stripe hosted Checkout: $1 entry (API prepaid) and budget+$1 top-ups."""
import os
from datetime import datetime, timezone

from app import db

ENTRY_AMOUNT_USD = 1.0
SERVICE_FEE_USD = 1.0

class BillingConfig:
  def __init__(self, enabled, secret_key, webhook_secret, app_base_url, stripe_module=None):
    self.enabled = enabled
    self.secret_key = secret_key
    self.webhook_secret = webhook_secret
    self.app_base_url = (app_base_url or "http://127.0.0.1:8000").rstrip("/")
    self.stripe = stripe_module

  @classmethod
  def from_env(cls, enabled=None, stripe_module=None):
    secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    enabled = enabled if enabled is not None else bool(secret)
    return cls(
      enabled=enabled,
      secret_key=secret,
      webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip(),
      app_base_url=os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").strip(),
      stripe_module=stripe_module,
    )

  def configured(self):
    return bool(self.enabled and self.secret_key)

def _stripe_client(config):
  if config.stripe: return config.stripe
  import stripe
  stripe.api_key = config.secret_key
  return stripe

def topup_charge_usd(budget_usd):
  return round(float(budget_usd) + SERVICE_FEE_USD, 2)

def _cents(usd):
  return int(round(float(usd) * 100))

def create_entry_checkout(config):
  stripe = _stripe_client(config)
  session = stripe.checkout.Session.create(
    mode="payment",
    line_items=[{"price_data": {
      "currency": "usd",
      "unit_amount": _cents(ENTRY_AMOUNT_USD),
      "product_data": {"name": "More Mentally Stable X Experience — API budget"},
    }, "quantity": 1}],
    success_url=f"{config.app_base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
    cancel_url=f"{config.app_base_url}/billing/cancel",
    metadata={"kind": "entry", "budget_credit_usd": str(ENTRY_AMOUNT_USD), "fee_usd": "0"},
  )
  return session

def create_topup_checkout(config, user_id, stripe_customer_id, budget_usd):
  stripe = _stripe_client(config)
  charge = topup_charge_usd(budget_usd)
  session = stripe.checkout.Session.create(
    mode="payment",
    customer=stripe_customer_id or None,
    line_items=[{"price_data": {
      "currency": "usd",
      "unit_amount": _cents(charge),
      "product_data": {"name": f"API budget top-up (${budget_usd:.2f}) + service fee"},
    }, "quantity": 1}],
    success_url=f"{config.app_base_url}/billing/topup/success?session_id={{CHECKOUT_SESSION_ID}}",
    cancel_url=f"{config.app_base_url}/settings?billing=cancelled",
    metadata={
      "kind": "topup", "user_id": str(user_id), "budget_credit_usd": str(budget_usd),
      "fee_usd": str(SERVICE_FEE_USD), "amount_usd": str(charge),
    },
  )
  return session

def retrieve_checkout_session(config, session_id):
  stripe = _stripe_client(config)
  return stripe.checkout.Session.retrieve(session_id, expand=["payment_intent"])

def session_is_paid(session):
  return session.get("payment_status") == "paid" or session.get("status") == "complete"

def apply_paid_session(conn, session):
  """Idempotent: credit entry or top-up from a paid Checkout Session."""
  sid = session["id"]
  meta = session.get("metadata") or {}
  kind = meta.get("kind", "entry")
  pi = session.get("payment_intent")
  payment_intent_id = pi if isinstance(pi, str) else (pi or {}).get("id")
  customer = session.get("customer")
  amount_usd = (session.get("amount_total") or 0) / 100.0
  paid_at = datetime.now(timezone.utc)
  if kind == "topup":
    user_id = int(meta["user_id"])
    return db.apply_topup_payment(conn, user_id=user_id, checkout_session_id=sid,
      payment_intent_id=payment_intent_id, budget_credit_usd=float(meta["budget_credit_usd"]),
      fee_usd=float(meta.get("fee_usd", SERVICE_FEE_USD)), amount_usd=amount_usd)
  user_id = int(meta["user_id"]) if meta.get("user_id") else None
  if user_id:
    return db.apply_entry_payment(conn, user_id=user_id, checkout_session_id=sid,
      payment_intent_id=payment_intent_id, amount_usd=ENTRY_AMOUNT_USD,
      stripe_customer_id=customer, paid_at=paid_at)
  return {"pending_user": True, "checkout_session_id": sid, "stripe_customer_id": customer,
    "payment_intent_id": payment_intent_id, "amount_usd": ENTRY_AMOUNT_USD}

def link_entry_payment_to_user(conn, checkout_session_id, user_id, stripe_customer_id=None):
  """Attach a paid entry session to a user after OAuth (first signup)."""
  row = conn.execute(
    "SELECT * FROM billing_payments WHERE checkout_session_id = ?", (checkout_session_id,)).fetchone()
  if row and row["user_id"]:
    return db.get_billing_account(conn, user_id=row["user_id"])
  paid_at = datetime.now(timezone.utc)
  return db.apply_entry_payment(conn, user_id=user_id, checkout_session_id=checkout_session_id,
    payment_intent_id=row["payment_intent_id"] if row else None, amount_usd=ENTRY_AMOUNT_USD,
    stripe_customer_id=stripe_customer_id, paid_at=paid_at)

def refund_unused_budget(config, conn, billing_row):
  """Refund unused API budget for a closed period. Returns Stripe refund id or None."""
  unused = db.unused_budget_usd(billing_row)
  if unused <= 0: return None
  payments = db.list_payments_for_user(conn, billing_row["user_id"])
  pi = None
  for p in payments:
    if p.get("payment_intent_id"): pi = p["payment_intent_id"]; break
  if not pi: return None
  stripe = _stripe_client(config)
  refund = stripe.Refund.create(payment_intent=pi, amount=_cents(unused),
    metadata={"kind": "unused_api_budget", "user_id": str(billing_row["user_id"])})
  db.record_period_refund(conn, billing_row["user_id"], billing_row["id"], unused,
    billing_row["period_start"], billing_row["period_end"], stripe_refund_id=refund["id"])
  return refund["id"]

def close_due_periods(config, conn, now=None):
  """Daily job: refund unused budget and close ended periods."""
  closed = []
  for billing in db.billing_accounts_due_for_close(conn, now=now):
    refund_id = None
    try: refund_id = refund_unused_budget(config, conn, billing)
    except Exception: pass
    db.close_billing_period(conn, billing["user_id"], now=now)
    closed.append(billing["user_id"])
  return closed

def verify_webhook(config, payload, sig_header):
  stripe = _stripe_client(config)
  return stripe.Webhook.construct_event(payload, sig_header, config.webhook_secret)

def handle_webhook_event(conn, event):
  if event["type"] != "checkout.session.completed": return None
  session = event["data"]["object"]
  if not session_is_paid(session): return None
  return apply_paid_session(conn, session)
