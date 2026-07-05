"""Console entry points."""

def dev():
  import uvicorn
  uvicorn.run("app.main:app", reload=True)
