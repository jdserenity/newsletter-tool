"""APScheduler jobs: weekly fetch (Monday 06:00 UTC) and background like queue."""
from app.env import load_env
load_env()

from apscheduler.schedulers.background import BackgroundScheduler

LIKE_QUEUE_POLL_SECONDS = 15

def run_job(db_path=None):
  from app import db
  from app.fetch.runner import run_weekly_fetch
  conn = db.connect(db_path)
  try: return run_weekly_fetch(conn)
  finally: conn.close()

def process_likes_job(db_path=None):
  from app import auth, db
  from app.user_actions import UserActionsClient, process_like_queue
  conn = db.connect(db_path)
  try: process_like_queue(conn, auth_config=auth.AuthConfig.from_env(), actions_client=UserActionsClient())
  finally: conn.close()

def start_scheduler(db_path=None):
  scheduler = BackgroundScheduler(timezone="UTC")
  scheduler.add_job(run_job, "cron", day_of_week="mon", hour=6, kwargs={"db_path": db_path}, id="weekly_fetch")
  scheduler.add_job(process_likes_job, "interval", seconds=LIKE_QUEUE_POLL_SECONDS,
    kwargs={"db_path": db_path}, id="like_queue", max_instances=1)
  scheduler.start()
  return scheduler
