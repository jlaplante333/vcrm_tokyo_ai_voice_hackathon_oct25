import os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .search import es_client, ensure_index, search_products, get_index_name, recent_products, count_products
from .auth import (
    ensure_users_index,
    require_user,
    issue_jwt,
    upsert_user_from_google,
    find_user_by_email,
    create_user_email,
    verify_password,
)
import json
import requests
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests


app = FastAPI(title="CRMBLR")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.auto_reload = True


@app.on_event("startup")
def on_startup():
    ensure_index()
    try:
        ensure_users_index()
    except Exception:
        # If ES not ready, we still let the app start
        pass


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # Workspace is the main app; client-side script ensures auth and redirects if missing
    return templates.TemplateResponse(
        "split.html",
        {"request": request},
    )


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    hits = []
    if q.strip():
        hits = search_products(q)
    return templates.TemplateResponse(
        "_results.html",
        {"request": request, "hits": hits, "hits_json": json.dumps(hits)},
    )


@app.get("/workspace", response_class=HTMLResponse)
def workspace(request: Request):
    return templates.TemplateResponse(
        "split.html",
        {"request": request},
    )


@app.get("/token")
def mint_ephemeral_token(user=Depends(require_user)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JSONResponse({"error": "OPENAI_API_KEY not configured"}, status_code=500)
    session_config = {
        "session": {
            "type": "realtime",
            "model": "gpt-realtime",
            "audio": {"output": {"voice": "marin"}},
        }
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=session_config,
            timeout=10,
        )
        return Response(resp.text, status_code=resp.status_code, media_type="application/json")
    except requests.RequestException as e:
        return JSONResponse({"error": "Failed to generate token"}, status_code=500)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    return templates.TemplateResponse("login.html", {"request": request, "google_client_id": google_client_id})


@app.post("/auth/google")
def auth_google(payload: dict):
    credential = payload.get("credential")
    if not credential:
        return JSONResponse({"error": "Missing credential"}, status_code=400)
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        return JSONResponse({"error": "GOOGLE_CLIENT_ID not configured"}, status_code=500)
    try:
        idinfo = google_id_token.verify_oauth2_token(credential, google_requests.Request(), audience=client_id)
        # Upsert user in ES
        user = upsert_user_from_google(idinfo)
        # Issue JWT
        token = issue_jwt({
            "sub": user["id"],
            "email": user.get("email"),
            "name": user.get("name"),
            "picture": user.get("picture"),
        })
        return JSONResponse({"token": token})
    except Exception as e:
        return JSONResponse({"error": "Invalid Google credential"}, status_code=401)


@app.get("/me")
def me(user=Depends(require_user)):
    return user


@app.post("/auth/signup")
def auth_signup(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    name = payload.get("name")
    if not email or not password:
        return JSONResponse({"error": "Email and password required"}, status_code=400)
    existing = find_user_by_email(email)
    if existing and existing.get("password_hash"):
        return JSONResponse({"error": "User already exists"}, status_code=400)
    user = existing or create_user_email(email, password, name)
    if existing and not existing.get("password_hash"):
        # Convert a Google-only user into one with password by setting hash
        from .auth import hash_password
        existing["password_hash"] = hash_password(password)
        es_client.index(index=os.getenv("ES_USERS_INDEX", "users"), id=existing["id"], document=existing, refresh="wait_for")
        user = existing
    token = issue_jwt({
        "sub": user["id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
    })
    return JSONResponse({"token": token})


@app.post("/auth/login")
def auth_login(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        return JSONResponse({"error": "Email and password required"}, status_code=400)
    user = find_user_by_email(email)
    if not user or not user.get("password_hash"):
        return JSONResponse({"error": "Invalid credentials"}, status_code=401)
    if not verify_password(password, user["password_hash"]):
        return JSONResponse({"error": "Invalid credentials"}, status_code=401)
    token = issue_jwt({
        "sub": user["id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
    })
    return JSONResponse({"token": token})
