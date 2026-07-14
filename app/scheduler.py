"""APScheduler: Mon + Thu 06:00 UTC. Weekly cadence skips Thursday at runtime."""
from datetime import datetime, timezone

from app.env import load_env
load_env()

from apscheduler.schedulers.background import BackgroundScheduler

def should_run_fetch(now=None, cadence="twice_weekly"):
  """True when today's weekday matches the cadence (Mon for weekly; Mon or Thu for twice)."""
  now = now or datetime.now(timezone.utc)
  if cadence == "weekly": return now.weekday() == 0
  return now.weekday() in (0, 3)

def run_job(db_path=None, now=None):
  from app import db
  from app.fetch.runner import run_weekly_fetch
  conn = db.connect(db_path)
  try:
    now = now or datetime.now(timezone.utc)
    cadence = db.get_app_settings(conn)["cadence"]
    if not should_run_fetch(now, cadence): return []
    return run_weekly_fetch(conn, now=now, db_path=db_path)
  finally: conn.close()

def run_billing_close(db_path=None, now=None):
  from app import billing, db
  config = billing.BillingConfig.from_env()
  if not config.configured(): return []
  conn = db.connect(db_path)
  try: return billing.close_due_periods(config, conn, now=now)
  finally: conn.close()

def start_scheduler(db_path=None, billing_enabled=False):
  scheduler = BackgroundScheduler(timezone="UTC")
  scheduler.add_job(run_job, "cron", day_of_week="mon,thu", hour=6,
    kwargs={"db_path": db_path}, id="scheduled_fetch")
  if billing_enabled:
    scheduler.add_job(run_billing_close, "cron", hour=7, kwargs={"db_path": db_path}, id="billing_close")
  scheduler.start()
  return scheduler
