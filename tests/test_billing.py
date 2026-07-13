from datetime import datetime, timezone
import calendar

import pytest

from app import db

def test_billing_period_end_is_one_calendar_month():
  start = datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc)
  end = db.billing_period_end(start)
  assert end == datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)

def test_remaining_budget(conn):
  uid = db.upsert_user(conn, "99", "alice", "Alice")
  db.create_billing_account(conn, uid, stripe_customer_id="cus_1", period_start="2026-06-01T00:00:00Z",
    period_end="2027-07-01T00:00:00Z", budget_usd=1.0, spent_usd=0.35)
  row = db.get_billing_account(conn, user_id=uid)
  assert db.remaining_budget(row) == pytest.approx(0.65)

def test_topup_charge_is_budget_plus_one():
  from app.billing import topup_charge_usd
  assert topup_charge_usd(5.0) == pytest.approx(6.0)

def test_record_api_call_debits_billing(conn):
  uid = db.upsert_user(conn, "99", "alice", "Alice")
  db.create_billing_account(conn, uid, stripe_customer_id="cus_1", period_start="2026-06-01T00:00:00Z",
    period_end="2027-07-01T00:00:00Z", budget_usd=1.0, spent_usd=0.0)
  db.record_api_call(conn, 1, "users/:id/tweets", 10, 0.05, user_id=uid)
  row = db.get_billing_account(conn, user_id=uid)
  assert row["spent_usd"] == pytest.approx(0.05)

def test_record_api_call_raises_when_budget_exhausted(conn):
  uid = db.upsert_user(conn, "99", "alice", "Alice")
  db.create_billing_account(conn, uid, stripe_customer_id="cus_1", period_start="2026-06-01T00:00:00Z",
    period_end="2027-07-01T00:00:00Z", budget_usd=1.0, spent_usd=0.99)
  with pytest.raises(db.BudgetExceededError):
    db.record_api_call(conn, 1, "users/:id/tweets", 10, 0.05, user_id=uid)

def test_apply_entry_payment_credits_one_dollar_budget(conn):
  uid = db.upsert_user(conn, "99", "alice", "Alice")
  paid_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
  db.apply_entry_payment(conn, user_id=uid, checkout_session_id="cs_entry", payment_intent_id="pi_entry",
    amount_usd=1.0, stripe_customer_id="cus_new", paid_at=paid_at)
  row = db.get_billing_account(conn, user_id=uid)
  assert row["budget_usd"] == pytest.approx(1.0)
  assert row["spent_usd"] == pytest.approx(0.0)
  assert row["period_start"] == "2026-03-15T10:00:00Z"
  assert row["period_end"] == db.billing_period_end(paid_at).strftime("%Y-%m-%dT%H:%M:%SZ")

def test_apply_topup_adds_budget_and_fee(conn):
  uid = db.upsert_user(conn, "99", "alice", "Alice")
  db.create_billing_account(conn, uid, stripe_customer_id="cus_1", period_start="2026-06-01T00:00:00Z",
    period_end="2027-07-01T00:00:00Z", budget_usd=1.0, spent_usd=1.0, status="exhausted")
  db.apply_topup_payment(conn, user_id=uid, checkout_session_id="cs_top", payment_intent_id="pi_top",
    budget_credit_usd=5.0, fee_usd=1.0, amount_usd=6.0)
  row = db.get_billing_account(conn, user_id=uid)
  assert row["budget_usd"] == pytest.approx(5.0)
  assert row["spent_usd"] == pytest.approx(0.0)
  assert row["status"] == "active"

def test_cancel_keeps_access_until_period_end(conn):
  uid = db.upsert_user(conn, "99", "alice", "Alice")
  db.create_billing_account(conn, uid, stripe_customer_id="cus_1", period_start="2026-06-01T00:00:00Z",
    period_end="2027-07-01T00:00:00Z", budget_usd=1.0, spent_usd=0.2)
  db.cancel_billing(conn, uid)
  row = db.get_billing_account(conn, user_id=uid)
  assert row["cancelled_at"] is not None
  assert row["status"] == "cancelled"
  assert db.remaining_budget(row) == pytest.approx(0.8)

def test_unused_refund_amount(conn):
  uid = db.upsert_user(conn, "99", "alice", "Alice")
  db.create_billing_account(conn, uid, stripe_customer_id="cus_1", period_start="2026-06-01T00:00:00Z",
    period_end="2027-07-01T00:00:00Z", budget_usd=1.0, spent_usd=0.4)
  assert db.unused_budget_usd(db.get_billing_account(conn, user_id=uid)) == pytest.approx(0.6)
