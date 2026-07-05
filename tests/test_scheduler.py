from app.scheduler import start_scheduler

def test_start_scheduler_registers_weekly_fetch_only(tmp_path):
  scheduler = start_scheduler(db_path=str(tmp_path / "sched.db"))
  jobs = {j.id for j in scheduler.get_jobs()}
  assert jobs == {"weekly_fetch"}
  scheduler.shutdown(wait=False)
