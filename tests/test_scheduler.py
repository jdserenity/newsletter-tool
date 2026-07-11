from datetime import datetime, timezone

from app.scheduler import should_run_fetch, start_scheduler

def test_should_run_fetch_weekly_monday_only():
  mon = datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc)
  thu = datetime(2026, 7, 9, 6, 0, tzinfo=timezone.utc)
  assert should_run_fetch(mon, "weekly") is True
  assert should_run_fetch(thu, "weekly") is False

def test_should_run_fetch_twice_weekly_mon_and_thu():
  mon = datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc)
  thu = datetime(2026, 7, 9, 6, 0, tzinfo=timezone.utc)
  wed = datetime(2026, 7, 8, 6, 0, tzinfo=timezone.utc)
  assert should_run_fetch(mon, "twice_weekly") is True
  assert should_run_fetch(thu, "twice_weekly") is True
  assert should_run_fetch(wed, "twice_weekly") is False

def test_start_scheduler_registers_mon_and_thu_fetch(tmp_path):
  scheduler = start_scheduler(db_path=str(tmp_path / "sched.db"))
  jobs = {j.id: j for j in scheduler.get_jobs()}
  assert set(jobs) == {"scheduled_fetch"}
  # Cron fires Mon and Thu; weekly cadence skips Thu at runtime.
  assert "mon" in str(jobs["scheduled_fetch"].trigger).lower()
  assert "thu" in str(jobs["scheduled_fetch"].trigger).lower()
  scheduler.shutdown(wait=False)
