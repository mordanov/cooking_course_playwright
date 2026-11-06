"""Auth-gated static file server for the cooking course offline site."""
import datetime
import os
from pathlib import Path

import jwt
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

_SECRET = os.environ["JWT_SECRET"]
_USER = os.environ["GC_EMAIL"]
_PASS = os.environ["GC_PASSWORD"]

_LOGIN_HTML = """\
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вход — Кулинарный курс</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100dvh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f0faf9;
    font: 16px/1.5 system-ui, -apple-system, sans-serif;
  }}
  form {{
    width: 100%;
    max-width: 360px;
    padding: 2rem;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 16px #0d948820;
  }}
  h1 {{ margin: 0 0 1.5rem; font-size: 1.25rem; color: #134e4a; }}
  label {{ display: block; font-size: .875rem; color: #555; margin-bottom: .25rem; }}
  input {{
    display: block; width: 100%; padding: .625rem .75rem;
    border: 1px solid #d1d5db; border-radius: 6px;
    font-size: 1rem; margin-bottom: 1rem;
    outline: none; transition: border-color .15s;
  }}
  input:focus {{ border-color: #0d9488; }}
  button {{
    width: 100%; padding: .75rem;
    background: #0d9488; color: #fff;
    border: none; border-radius: 6px;
    font-size: 1rem; cursor: pointer;
    transition: background .15s;
  }}
  button:hover {{ background: #0f766e; }}
  .err {{ color: #dc2626; font-size: .875rem; margin-bottom: 1rem; }}
</style>
</head>
<body>
<form method="post" action="/login">
  <h1>🍳 Кулинарный курс</h1>
  {error}
  <label for="email">Email</label>
  <input id="email" name="email" type="email" autocomplete="username" required>
  <label for="password">Пароль</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  <button type="submit">Войти</button>
</form>
</body>
</html>"""

_COOKIE = "cooking_token"
_DAYS = 30


class _AuthMiddleware(BaseHTTPMiddleware):
    _public = {"/login", "/health", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._public:
            return await call_next(request)
        token = request.cookies.get(_COOKIE, "")
        try:
            jwt.decode(token, _SECRET, algorithms=["HS256"])
            return await call_next(request)
        except Exception:
            return RedirectResponse("/login", status_code=302)


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(_AuthMiddleware)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return _LOGIN_HTML.format(error="")


@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    if email != _USER or password != _PASS:
        return HTMLResponse(
            _LOGIN_HTML.format(error='<p class="err">Неверный email или пароль.</p>'),
            status_code=401,
        )
    token = jwt.encode(
        {"exp": datetime.datetime.utcnow() + datetime.timedelta(days=_DAYS)},
        _SECRET,
        algorithm="HS256",
    )
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        _COOKIE, token, httponly=True, samesite="lax", max_age=_DAYS * 86400
    )
    return resp


@app.get("/health")
async def health():
    return {"ok": True}


_offline = Path("offline")
if _offline.exists():
    app.mount("/", StaticFiles(directory=str(_offline), html=True), name="static")
