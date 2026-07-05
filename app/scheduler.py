"""APScheduler weekly job: Monday 06:00 UTC, fetch last complete week and build newsletters."""
from app.env import load_env
load_env()

from apscheduler.schedulers.background import BackgroundScheduler

def run_job(db_path=None):
  from app import db
  from app.fetch.runner import run_weekly_fetch
  conn = db.connect(db_path)
  try: return run_weekly_fetch(conn, db_path=db_path)
  finally: conn.close()

def start_scheduler(db_path=None):
  scheduler = BackgroundScheduler(timezone="UTC")
  scheduler.add_job(run_job, "cron", day_of_week="mon", hour=6, kwargs={"db_path": db_path}, id="weekly_fetch")
  scheduler.start()
  return scheduler
