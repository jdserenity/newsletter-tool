"""Console entry points."""

def _open_db():
  from app.env import load_env
  load_env()
  from app import db
  path = db.resolve_db_path()
  return path, db.connect(path)

def db_status():
  """Print a quick overview of what's in the database."""
  from app import db
  path, conn = _open_db()
  try:
    o = db.database_overview(conn)
    print(f"Database: {path}")
    print(f"Fetch week: {o['week_start'][:10]} → {o['week_end'][:10]}")
    print(f"Totals: {o['tweet_count']} tweets · {o['edition_count']} editions · "
          f"${o['api_cost_usd']:.3f} API · "
          f"OAuth {'yes' if o['oauth_signed_in'] else 'no'}")
    active = sum(1 for a in o["accounts"] if a["active"])
    inactive = sum(1 for a in o["accounts"] if not a["active"])
    print(f"Accounts: {active} active" + (f", {inactive} inactive" if inactive else ""))
    for a in o["accounts"]:
      if not a["active"]: continue
      name = f" ({a['display_name']})" if a.get("display_name") else ""
      if a["edition_items"] is not None:
        wk = a["edition_week_start"][:10] if a.get("edition_week_start") else "?"
        ed = f"{a['tweets_in_week']} tweets · {a['edition_items']} in newsletter ({wk})"
      else:
        ed = f"{a['tweets_in_week']} in fetch week · no newsletter"
      feedback = f"{a['liked_count']} liked · {a['disliked_count']} disliked"
      print(f"  @{a['handle']}{name}: {a['tweet_count']} stored · {ed} · {feedback} · API ${a['total_cost_usd']:.3f}")
  finally:
    conn.close()

def dev():
  import uvicorn
  uvicorn.run("app.main:create_app", factory=True, reload=True)

def fetch():
  """Fetch last complete week and build newsletters."""
  from app.fetch.runner import run_weekly_fetch
  path, conn = _open_db()
  try:
    print(f"Database: {path}")
    results = run_weekly_fetch(conn)
    for handle, cost in results:
      print(f"{handle}: ${cost:.3f}")
    if not results:
      print("No active accounts.")
  finally:
    conn.close()

def db_status_entry():
  db_status()
