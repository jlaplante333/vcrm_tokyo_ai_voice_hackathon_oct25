import os
from typing import Dict, Generator, Iterable, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from elasticsearch import Elasticsearch, helpers


# Config via env (keep it minimal and explicit)
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "products")
API_BASE = os.getenv("API_BASE", "https://dummyjson.com/products")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "100"))
MAX_DOCS = int(os.getenv("MAX_DOCS", "0"))  # 0 = no cap


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def es_client() -> Elasticsearch:
    return Elasticsearch([ELASTICSEARCH_URL])


def ensure_index(es: Elasticsearch) -> None:
    if es.indices.exists(index=ES_INDEX):
        return
    es.indices.create(
        index=ES_INDEX,
        body={
            "settings": {"analysis": {"analyzer": {"default": {"type": "standard"}}}},
            "mappings": {
                "properties": {
                    "title": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                    "description": {"type": "text"},
                    "category": {"type": "keyword"},
                    "price": {"type": "float"},
                    "url": {"type": "keyword", "index": False},
                    "image_url": {"type": "keyword", "index": False},
                    "source": {"type": "keyword"},
                    "source_id": {"type": "keyword"},
                }
            },
        },
    )


def to_action(p: Dict[str, Any]) -> Dict[str, Any]:
    # Deterministic ID makes ingestion idempotent and safe to re-run.
    pid = str(p.get("id"))
    return {
        "_index": ES_INDEX,
        "_id": f"dummy-{pid}",
        "_source": {
            "title": p.get("title"),
            "description": p.get("description"),
            "category": p.get("category"),
            "price": float(p.get("price", 0)),
            "url": f"{API_BASE}/{pid}",
            "image_url": (p.get("thumbnail") or (p.get("images") or [None])[0]),
            "source": "dummyjson",
            "source_id": pid,
        },
    }


def fetch_actions(session: requests.Session) -> Generator[Dict[str, Any], None, None]:
    # Minimal pagination using limit/skip pattern
    fetched = 0
    remaining = MAX_DOCS if MAX_DOCS > 0 else None
    while True:
        limit = PAGE_SIZE if remaining is None else min(PAGE_SIZE, remaining)
        params = {"limit": limit, "skip": fetched}
        resp = session.get(API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            yield to_action(p)
        fetched += len(products)
        if remaining is not None:
            remaining -= len(products)
            if remaining <= 0:
                break


def main() -> None:
    session = make_session()
    es = es_client()
    ensure_index(es)

    # helpers.bulk handles batching internally and works with generators.
    success, errors = helpers.bulk(es, fetch_actions(session), stats_only=True)
    print(f"Indexed {success} docs ({errors} errors) into '{ES_INDEX}' at {ELASTICSEARCH_URL}")


if __name__ == "__main__":
    main()

