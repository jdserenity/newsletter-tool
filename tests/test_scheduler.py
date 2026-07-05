from app.scheduler import LIKE_QUEUE_POLL_SECONDS, process_likes_job, start_scheduler

def test_process_likes_job_runs_without_error(tmp_path, monkeypatch):
  monkeypatch.setattr("app.user_actions.process_like_queue", lambda *a, **k: False)
  process_likes_job(db_path=str(tmp_path / "sched.db"))

def test_start_scheduler_registers_like_queue_job(tmp_path):
  scheduler = start_scheduler(db_path=str(tmp_path / "sched.db"))
  jobs = {j.id: j for j in scheduler.get_jobs()}
  assert "weekly_fetch" in jobs
  assert "like_queue" in jobs
  assert jobs["like_queue"].trigger.interval.total_seconds() == LIKE_QUEUE_POLL_SECONDS
  scheduler.shutdown(wait=False)
