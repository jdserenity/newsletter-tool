import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from app.env import load_env
load_env()

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import auth, db
from app.scheduler import start_scheduler
from app.user_actions import UserActionsClient, follow_tracked_account

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def create_app(db_path=None, with_scheduler=True, auth_enabled=True, auth_config=None):
  path = str(db.resolve_db_path(db_path))
  auth_config = auth_config or auth.AuthConfig.from_env(enabled=auth_enabled)
  if auth_config.enabled and not auth_config.configured():
    raise RuntimeError("User auth is enabled but X_CLIENT_ID, X_CLIENT_SECRET, or SESSION_SECRET is missing")

  @asynccontextmanager
  async def lifespan(app):
    from app.user_actions import resume_like_drain_if_needed
    scheduler = start_scheduler(path) if with_scheduler else None
    resume_like_drain_if_needed(path)
    yield
    if scheduler: scheduler.shutdown(wait=False)

  app = FastAPI(title="newsletter-tool", lifespan=lifespan)
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
      db.save_oauth_session(conn(), me["id"], token["access_token"], token.get("refresh_token"))
      request.session.pop(auth.SESSION_OAUTH_STATE, None)
      request.session.pop(auth.SESSION_CODE_VERIFIER, None)
      return RedirectResponse("/", status_code=303)

    @app.post("/auth/logout")
    def auth_logout(request: Request):
      auth.clear_session(request)
      return RedirectResponse("/auth/login", status_code=303)

  def newsletter_cards(c):
    cards = []
    for a in db.list_accounts(c):
      a["total_cost"] = db.cost_for_account(c, a["id"])
      edition = db.latest_edition(c, a["id"])
      items = json.loads(edition["content_json"]) if edition else []
      cards.append({"account": a, "edition": edition, "entries": items})
    return cards

  @app.get("/", response_class=HTMLResponse)
  def home(request: Request):
    return render(request, "home.html", {"cards": newsletter_cards(conn())})

  @app.post("/accounts")
  def add_account(request: Request, handle: str = Form(...)):
    c = conn()
    account_id = None
    try: account_id = db.add_account(c, handle)
    except Exception: pass  # duplicate handle: just return to the list
    if account_id and auth_config.enabled:
      user = auth.session_user(request)
      token = request.session.get(auth.SESSION_ACCESS)
      if user and token:
        account = db.get_account(c, account_id=account_id)
        follow_tracked_account(c, UserActionsClient(), token, user["x_user_id"], account)
    return RedirectResponse("/", status_code=303)

  @app.post("/accounts/{account_id}/remove")
  def remove_account(account_id: int):
    db.remove_account(conn(), account_id)
    return RedirectResponse("/", status_code=303)

  @app.get("/accounts/{account_id}")
  def account_page(account_id: int):
    if not db.get_account(conn(), account_id=account_id): raise HTTPException(404)
    return RedirectResponse("/", status_code=303)

  @app.post("/accounts/{account_id}/settings")
  def save_settings(account_id: int, include_quotes: bool = Form(False),
                    include_replies: bool = Form(False), include_retweets: bool = Form(False)):
    db.update_settings(conn(), account_id, include_quotes=include_quotes,
                       include_replies=include_replies, include_retweets=include_retweets)
    return RedirectResponse("/", status_code=303)

  @app.get("/editions/{edition_id}", response_class=HTMLResponse)
  def edition_page(request: Request, edition_id: int):
    edition = db.get_edition(conn(), edition_id)
    if not edition: raise HTTPException(404)
    items = json.loads(edition["content_json"])
    return render(request, "edition.html", {"edition": edition, "items": items})

  @app.get("/feeds/{account_id}.xml")
  def account_feed(request: Request, account_id: int):
    from app.rss import newsletter_feed
    c = conn()
    account = db.get_account(c, account_id=account_id)
    if not account: raise HTTPException(404)
    editions = db.list_editions(c, account_id)
    base = str(request.base_url).rstrip("/")
    return Response(newsletter_feed(account, editions, base), media_type="application/rss+xml")

  return app
