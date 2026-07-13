import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from app.env import load_env
load_env()

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import auth, db
from app.fetch.runner import repair_missing_editions
from app.scheduler import start_scheduler
from app.user_actions import LikeActionError, like_tweet_on_x, unlike_tweet_on_x

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def create_app(db_path=None, with_scheduler=True, auth_enabled=True, auth_config=None):
  path = str(db.resolve_db_path(db_path))
  auth_config = auth_config or auth.AuthConfig.from_env(enabled=auth_enabled)
  if auth_config.enabled and not auth_config.configured():
    raise RuntimeError("User auth is enabled but X_CLIENT_ID, X_CLIENT_SECRET, or SESSION_SECRET is missing")

  @asynccontextmanager
  async def lifespan(app):
    scheduler = start_scheduler(path) if with_scheduler else None
    yield
    if scheduler: scheduler.shutdown(wait=False)

  app = FastAPI(title="More Mentally Stable X Experience", lifespan=lifespan)
  app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
  app.state.db_path = path
  app.state.auth_config = auth_config

  if auth_config.enabled:
    app.add_middleware(auth.RequireAuthMiddleware, config=auth_config)
    app.add_middleware(SessionMiddleware, secret_key=auth_config.session_secret, https_only=False)

  def conn(): return db.connect(path)

  def render(request: Request, name: str, ctx: dict):
    ctx = dict(ctx)
    if auth_config.enabled: ctx["user"] = auth.session_user(request)
    return templates.TemplateResponse(request, name, ctx)

  def after_authenticated_request(c, request: Request):
    """Persist OAuth tokens from the browser session into SQLite when present."""
    if not auth_config.enabled: return
    auth.persist_session_oauth(c, request)

  def owner_x_like(c, request: Request, tweet_id: str):
    """Like on X using the signed-in owner's token. Skipped when auth is disabled (tests)."""
    if not auth_config.enabled: return
    access, owner_id = auth.owner_access_token(c, request, auth_config)
    if not access or not owner_id:
      raise HTTPException(401, "Sign in with X to like tweets")
    try: like_tweet_on_x(access, owner_id, tweet_id)
    except LikeActionError as e: raise HTTPException(502, str(e)) from e

  def owner_x_unlike(c, request: Request, tweet_id: str):
    """Unlike on X when clearing local like. Best-effort; skips when auth is off."""
    if not auth_config.enabled: return
    access, owner_id = auth.owner_access_token(c, request, auth_config)
    if not access or not owner_id: return
    try: unlike_tweet_on_x(access, owner_id, tweet_id)
    except LikeActionError: pass

  if auth_config.enabled:
    @app.get("/auth/login", response_class=HTMLResponse)
    def auth_login_page(request: Request):
      return render(request, "login.html", {})

    @app.get("/auth/login/start")
    def auth_login_start(request: Request):
      state = secrets.token_urlsafe(32)
      verifier, challenge = auth.make_pkce_pair()
      request.session[auth.SESSION_OAUTH_STATE] = state
      request.session[auth.SESSION_CODE_VERIFIER] = verifier
      url = auth.build_authorize_url(
        auth_config.client_id, auth_config.callback_url, state, challenge, auth_config.scopes)
      return RedirectResponse(url, status_code=303)

    @app.get("/auth/callback")
    def auth_callback(request: Request, code: str = "", state: str = ""):
      if state != request.session.get(auth.SESSION_OAUTH_STATE):
        raise HTTPException(400, "Invalid OAuth state")
      verifier = request.session.get(auth.SESSION_CODE_VERIFIER)
      if not code or not verifier:
        raise HTTPException(400, "Missing authorization code")
      http = auth.http_client(auth_config)
      try:
        token = auth.exchange_code(http, auth_config.client_id, auth_config.client_secret,
          auth_config.callback_url, code, verifier)
        me = auth.fetch_me(http, token["access_token"])
      except Exception as e:
        raise HTTPException(400, f"OAuth token exchange failed: {e}") from e
      auth.store_user_session(request, token, me)
      db.save_oauth_session(conn(), me["id"], token["access_token"], token.get("refresh_token"),
        expires_at=auth.expires_at_from_token(token))
      request.session.pop(auth.SESSION_OAUTH_STATE, None)
      request.session.pop(auth.SESSION_CODE_VERIFIER, None)
      return RedirectResponse("/", status_code=303)

    @app.post("/auth/logout")
    def auth_logout(request: Request):
      auth.clear_session(request)
      return RedirectResponse("/", status_code=303)

  def newsletter_cards(c):
    from app.fetch.runner import period_bounds
    from app.newsletter import order_entries_unread_first
    cadence = db.get_app_settings(c)["cadence"]
    current_week_start, _ = period_bounds(cadence=cadence)
    cards = []
    for a in db.list_accounts(c):
      a["total_cost"] = db.cost_for_account(c, a["id"])
      edition = db.latest_edition(c, a["id"])
      week_start = edition["week_start"] if edition else current_week_start
      if db.is_newsletter_read(c, a["id"], week_start): continue
      items = json.loads(edition["content_json"]) if edition else []
      tweet_ids = [i["tweet_id"] for i in items if i.get("tweet_id")]
      read_ids = db.read_tweet_ids(c, tweet_ids)
      read_times = db.read_tweet_times(c, tweet_ids)
      liked_ids = db.liked_tweet_ids(c, tweet_ids)
      disliked_ids = db.disliked_tweet_ids(c, tweet_ids)
      items = order_entries_unread_first(items, read_ids, read_times)
      all_tweets_read = bool(tweet_ids) and all(tid in read_ids for tid in tweet_ids)
      cards.append({
        "account": a, "edition": edition, "entries": items,
        "week_start": week_start, "read_tweet_ids": read_ids,
        "read_tweet_times": read_times,
        "liked_tweet_ids": liked_ids, "disliked_tweet_ids": disliked_ids,
        "all_tweets_read": all_tweets_read})
    return cards

  @app.get("/", response_class=HTMLResponse)
  def home(request: Request):
    # Signed-out visitors (auth on) see the landing page; signed-in users get the app.
    if auth_config.enabled and not auth.session_user(request):
      return render(request, "landing.html", {})
    c = conn()
    repair_missing_editions(c)  # local only — no X API
    after_authenticated_request(c, request)
    return render(request, "home.html", {"cards": newsletter_cards(c)})

  @app.get("/settings", response_class=HTMLResponse)
  def settings_page(request: Request):
    c = conn()
    accounts = db.list_accounts(c)
    return render(request, "settings.html", {
      "accounts": accounts,
      "account_count": len(accounts),
      "month_cost_usd": db.total_api_cost(c, since=db.month_start_utc()),
      "app_settings": db.get_app_settings(c),
    })

  @app.post("/settings")
  def save_app_settings(request: Request, cadence: str = Form("twice_weekly"),
                        append_unread: bool = Form(False)):
    if cadence not in db.CADENCES: raise HTTPException(400, "Invalid cadence")
    db.update_app_settings(conn(), cadence=cadence, append_unread=append_unread)
    return RedirectResponse("/settings", status_code=303)

  @app.post("/accounts")
  def add_account(request: Request, handle: str = Form(...)):
    c = conn()
    account_id = None
    try: account_id = db.add_account(c, handle)
    except Exception: pass  # duplicate handle: just return to the list
    if account_id and auth_config.enabled:
      after_authenticated_request(c, request)
    return RedirectResponse("/", status_code=303)

  @app.post("/accounts/estimate")
  def estimate_account(handle: str = Form(...), include_replies: bool = Form(False),
                       include_retweets: bool = Form(False)):
    from app.fetch.client import XClient
    from app.fetch.estimate import estimate_fetch_cost
    h = handle.lstrip("@").strip()
    if not h: raise HTTPException(400, "Handle required")
    if db.get_account(conn(), handle=h): raise HTTPException(400, "Account already tracked")
    try:
      result = estimate_fetch_cost(XClient(), h, include_replies=include_replies, include_retweets=include_retweets)
    except Exception as e:
      raise HTTPException(502, f"X API estimate failed: {e}") from e
    return JSONResponse(result)

  @app.post("/accounts/{account_id}/remove")
  def remove_account(account_id: int):
    db.remove_account(conn(), account_id)
    return RedirectResponse("/settings", status_code=303)

  @app.get("/accounts/{account_id}")
  def account_page(account_id: int):
    if not db.get_account(conn(), account_id=account_id): raise HTTPException(404)
    return RedirectResponse("/", status_code=303)

  @app.post("/accounts/{account_id}/settings")
  def save_settings(request: Request, account_id: int, include_quotes: bool = Form(False),
                    include_replies: bool = Form(False), include_retweets: bool = Form(False)):
    # JSON for in-place UI (no page reload — reload was resetting carousel scroll to the left).
    if not db.get_account(conn(), account_id=account_id): raise HTTPException(404)
    db.update_settings(conn(), account_id, include_quotes=include_quotes,
                       include_replies=include_replies, include_retweets=include_retweets)
    if "application/json" in request.headers.get("accept", ""):
      return JSONResponse({"ok": True, "account_id": account_id,
        "include_quotes": include_quotes, "include_replies": include_replies,
        "include_retweets": include_retweets})
    return RedirectResponse("/", status_code=303)

  @app.post("/tweets/{tweet_id}/like")
  def like_tweet(request: Request, tweet_id: str):
    c = conn()
    owner_x_like(c, request, tweet_id)
    db.like_tweet(c, tweet_id)
    if "application/json" in request.headers.get("accept", ""):
      return JSONResponse({"ok": True, "tweet_id": tweet_id, "feedback": "like", "read": True, "liked_on_x": auth_config.enabled})
    return RedirectResponse("/", status_code=303)

  @app.post("/tweets/{tweet_id}/dislike")
  def dislike_tweet(request: Request, tweet_id: str):
    c = conn()
    if db.is_tweet_liked(c, tweet_id): owner_x_unlike(c, request, tweet_id)
    db.dislike_tweet(c, tweet_id)
    if "application/json" in request.headers.get("accept", ""):
      return JSONResponse({"ok": True, "tweet_id": tweet_id, "feedback": "dislike", "read": True})
    return RedirectResponse("/", status_code=303)

  @app.post("/tweets/{tweet_id}/read")
  def set_tweet_read(request: Request, tweet_id: str, read: bool = Form(False)):
    """read=true likes on X + locally; read=false unlikes on X and clears feedback."""
    c = conn()
    if read: owner_x_like(c, request, tweet_id); db.like_tweet(c, tweet_id)
    else:
      if db.is_tweet_liked(c, tweet_id): owner_x_unlike(c, request, tweet_id)
      db.clear_tweet_feedback(c, tweet_id)
    if "application/json" in request.headers.get("accept", ""):
      return JSONResponse({"ok": True, "tweet_id": tweet_id, "read": read,
        "feedback": "like" if read else None, "liked_on_x": read and auth_config.enabled})
    return RedirectResponse("/", status_code=303)

  @app.post("/accounts/{account_id}/read-newsletter")
  def set_newsletter_read(request: Request, account_id: int, week_start: str = Form(...)):
    c = conn()
    if not db.get_account(c, account_id=account_id): raise HTTPException(404)
    if not week_start.strip(): raise HTTPException(400, "week_start required")
    db.mark_newsletter_read(c, account_id, week_start.strip())
    if "application/json" in request.headers.get("accept", ""):
      return JSONResponse({"ok": True, "account_id": account_id, "week_start": week_start.strip()})
    return RedirectResponse("/", status_code=303)

  @app.get("/editions/{edition_id}", response_class=HTMLResponse)
  def edition_page(request: Request, edition_id: int):
    from app.newsletter import order_entries_unread_first
    c = conn()
    edition = db.get_edition(c, edition_id)
    if not edition: raise HTTPException(404)
    items = json.loads(edition["content_json"])
    tweet_ids = [i["tweet_id"] for i in items if i.get("tweet_id")]
    read_ids = db.read_tweet_ids(c, tweet_ids)
    read_times = db.read_tweet_times(c, tweet_ids)
    liked_ids = db.liked_tweet_ids(c, tweet_ids)
    disliked_ids = db.disliked_tweet_ids(c, tweet_ids)
    items = order_entries_unread_first(items, read_ids, read_times)
    return render(request, "edition.html", {
      "edition": edition, "items": items, "read_tweet_ids": read_ids,
      "read_tweet_times": read_times,
      "liked_tweet_ids": liked_ids, "disliked_tweet_ids": disliked_ids})

  @app.get("/feeds/{account_id}.xml")
  def account_feed(request: Request, account_id: int):
    from app.rss import newsletter_feed
    c = conn()
    account = db.get_account(c, account_id=account_id)
    if not account: raise HTTPException(404)
    if not account.get("active", 1): raise HTTPException(404)
    editions = db.list_editions(c, account_id)
    base = str(request.base_url).rstrip("/")
    # Public route (no session). Readers poll this URL without cookies.
    return Response(
      newsletter_feed(account, editions, base),
      media_type="application/rss+xml; charset=utf-8",
      headers={"Cache-Control": "public, max-age=300"})

  return app
