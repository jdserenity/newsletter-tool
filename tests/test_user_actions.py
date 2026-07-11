import httpx

from app.user_actions import LikeActionError, UserActionsClient, like_tweet_on_x, unlike_tweet_on_x

class FakeResponse:
  def __init__(self, status_code=200, body=None, text=""):
    self.status_code = status_code; self.body = body or {}; self.text = text or str(body or "")
    self.content = b"{}" if body is not None else b""
  def json(self): return self.body

class FakeHttp:
  def __init__(self, responses=None):
    self.responses = responses or {}; self.posts = []; self.deletes = []
  def post(self, path, headers=None, json=None):
    self.posts.append((path, headers or {}, json or {}))
    if path in self.responses: return self.responses[path]
    if json and json.get("tweet_id") and "likes" in path: return FakeResponse(200, {"data": {"liked": True}})
    return FakeResponse(200, {"data": {}})
  def delete(self, path, headers=None):
    self.deletes.append((path, headers or {}))
    if path in self.responses: return self.responses[path]
    if "likes" in path: return FakeResponse(200, {"data": {"liked": False}})
    return FakeResponse(200, {})

def test_like_tweet_posts_tweet_id():
  http = FakeHttp(); client = UserActionsClient(http=http)
  client.like_tweet("token", "99", "42")
  assert http.posts == [("/users/99/likes", {"Authorization": "Bearer token", "Content-Type": "application/json"}, {"tweet_id": "42"})]

def test_unlike_tweet_deletes_by_tweet_id():
  http = FakeHttp(); client = UserActionsClient(http=http)
  client.unlike_tweet("token", "99", "42")
  assert http.deletes == [("/users/99/likes/42", {"Authorization": "Bearer token"})]

def test_like_tweet_raises_on_x_error():
  http = FakeHttp({"/users/99/likes": FakeResponse(403, text='{"title":"Forbidden"}')})
  try:
    UserActionsClient(http=http).like_tweet("token", "99", "42")
    assert False, "expected LikeActionError"
  except LikeActionError as e:
    assert "403" in str(e)

def test_like_tweet_on_x_helper():
  http = FakeHttp()
  like_tweet_on_x("tok", "77", "5", actions_client=UserActionsClient(http=http))
  assert http.posts[0][2]["tweet_id"] == "5"

def test_unlike_tweet_on_x_helper():
  http = FakeHttp()
  unlike_tweet_on_x("tok", "77", "5", actions_client=UserActionsClient(http=http))
  assert http.deletes[0][0] == "/users/77/likes/5"
