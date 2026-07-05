import json
from contextlib import asynccontextmanager
from pathlib import Path

from app.env import load_env
load_env()

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db
from app.scheduler import start_scheduler

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def create_app(db_path=None, with_scheduler=True):
  path = str(db.resolve_db_path(db_path))
  @asynccontextmanager
  async def lifespan(app):
    scheduler = start_scheduler(path) if with_scheduler else None
    yield
    if scheduler: scheduler.shutdown(wait=False)

  app = FastAPI(title="newsletter-tool", lifespan=lifespan)
  app.state.db_path = path

  def conn(): return db.connect(path)

  @app.get("/", response_class=HTMLResponse)
  def home(request: Request):
    c = conn()
    accounts = db.list_accounts(c)
    for a in accounts: a["total_cost"] = db.cost_for_account(c, a["id"])
    digests = db.list_digests(c)
    return templates.TemplateResponse(request, "home.html", {"accounts": accounts, "digests": digests})

  @app.post("/accounts")
  def add_account(handle: str = Form(...)):
    c = conn()
    try: db.add_account(c, handle)
    except Exception: pass  # duplicate handle: just return to the list
    return RedirectResponse("/", status_code=303)

  @app.post("/accounts/{account_id}/remove")
  def remove_account(account_id: int):
    db.remove_account(conn(), account_id)
    return RedirectResponse("/", status_code=303)

  @app.get("/accounts/{account_id}", response_class=HTMLResponse)
  def account_page(request: Request, account_id: int):
    c = conn()
    account = db.get_account(c, account_id=account_id)
    if not account: raise HTTPException(404)
    account["total_cost"] = db.cost_for_account(c, account_id)
    digests = db.list_digests(c, account_id)
    return templates.TemplateResponse(request, "account.html", {"account": account, "digests": digests})

  @app.post("/accounts/{account_id}/settings")
  def save_settings(account_id: int, include_quotes: bool = Form(False),
                    include_replies: bool = Form(False), include_retweets: bool = Form(False)):
    db.update_settings(conn(), account_id, include_quotes=include_quotes,
                       include_replies=include_replies, include_retweets=include_retweets)
    return RedirectResponse(f"/accounts/{account_id}", status_code=303)

  @app.get("/digests/{digest_id}", response_class=HTMLResponse)
  def digest_page(request: Request, digest_id: int):
    digest = db.get_digest(conn(), digest_id)
    if not digest: raise HTTPException(404)
    items = json.loads(digest["content_json"])
    return templates.TemplateResponse(request, "digest.html", {"digest": digest, "items": items})

  @app.get("/feeds/{account_id}.xml")
  def account_feed(request: Request, account_id: int):
    from app.rss import digest_feed
    c = conn()
    account = db.get_account(c, account_id=account_id)
    if not account: raise HTTPException(404)
    digests = db.list_digests(c, account_id)
    base = str(request.base_url).rstrip("/")
    return Response(digest_feed(account, digests, base), media_type="application/rss+xml")

  return app

app = create_app()  # path from DATABASE_PATH env or ~/.local/share/newsletter-tool/newsletter.db
