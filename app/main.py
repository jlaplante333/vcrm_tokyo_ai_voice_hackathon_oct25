import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .search import es_client, ensure_index, search_products, get_index_name, recent_products, count_products
import json


app = FastAPI(title="nibbins")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.auto_reload = True


@app.on_event("startup")
def on_startup():
    ensure_index()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = ""):
    hits = []
    recent = []
    # Precompute product count for dynamic placeholder
    total_count = count_products()
    placeholder_text = f"Search {total_count:,} nibbs" if total_count else "Search nibbs"
    if q.strip():
        hits = search_products(q)
    else:
        # Show a larger set of recent items on the homepage
        recent = recent_products(size=200)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "hits": hits,
            "hits_json": json.dumps(hits),
            "recent": recent,
            "q": q,
            "placeholder_text": placeholder_text,
        },
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
