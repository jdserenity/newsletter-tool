"""Console entry points."""

def dev():
  import uvicorn
  uvicorn.run("app.main:create_app", factory=True, reload=True)
