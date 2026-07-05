"""Console entry points."""

def dev():
  import uvicorn
  uvicorn.run("app.main:create_app", factory=True, reload=True)

def fetch():
  """Fetch last complete week, build newsletters, then drain the like queue (blocking)."""
  from app.env import load_env
  load_env()
  from app import auth, db
  from app.fetch.runner import run_weekly_fetch
  from app.user_actions import UserActionsClient, drain_like_queue
  path = db.resolve_db_path()
  conn = db.connect(path)
  try:
    results = run_weekly_fetch(conn)  # enqueue only; no background thread
    queued = db.like_queue_size(conn)
    for handle, cost in results:
      print(f"{handle}: ${cost:.3f}")
    if not results:
      print("No active accounts.")
    elif queued:
      print(f"Draining {queued} queued likes (paced; may take a while)...")
      liked = drain_like_queue(conn, auth_config=auth.AuthConfig.from_env(), actions_client=UserActionsClient())
      print(f"Liked {liked} tweets.")
  finally:
    conn.close()
