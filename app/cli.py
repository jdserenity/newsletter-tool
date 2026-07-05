"""Console entry points."""

def dev():
  from app.env import load_env
  load_env()
  import uvicorn
  uvicorn.run("app.main:app", reload=True)
