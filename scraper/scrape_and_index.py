import os
import time
from typing import Dict, Generator, Iterable

import requests
from elasticsearch import Elasticsearch, helpers


ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "products")

# Ingestion tuning
BULK_CHUNK_SIZE = int(os.getenv("BULK_CHUNK_SIZE", "500"))
BULK_REQUEST_TIMEOUT = int(os.getenv("BULK_REQUEST_TIMEOUT", "60"))
BULK_MAX_RETRIES = int(os.getenv("BULK_MAX_RETRIES", "3"))
TARGET_COUNT = int(os.getenv("TARGET_COUNT", "0"))  # 0 means "no explicit cap"
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "200"))


def es_client() -> Elasticsearch:
    return Elasticsearch([ES_URL])


def ensure_index(es: Elasticsearch) -> None:
    if es.indices.exists(index=ES_INDEX):
        return
    es.indices.create(
        index=ES_INDEX,
        body={
            "settings": {
                "analysis": {"analyzer": {"default": {"type": "standard"}}}
            },
            "mappings": {
                "properties": {
                    "title": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                    "description": {"type": "text"},
                    "category": {"type": "keyword"},
                    "price": {"type": "float"},
                    "url": {"type": "keyword", "index": False},
                    "image_url": {"type": "keyword", "index": False},
                    "source": {"type": "keyword"},
                    "source_id": {"type": "keyword"}
                }
            },
        },
    )


def build_action(p: Dict) -> Dict:
    return {
        "_index": ES_INDEX,
        "_id": f"dummy-{p['id']}",  # deterministic for idempotency
        "_op_type": "index",  # replace if exists
        "_source": {
            "title": p.get("title"),
            "description": p.get("description"),
            "category": p.get("category"),
            "price": float(p.get("price", 0)),
            "url": f"https://dummyjson.com/products/{p['id']}",
            "image_url": (p.get("thumbnail") or (p.get("images") or [None])[0]),
            "source": "dummyjson",
            "source_id": str(p.get("id")),
        },
    }


def fetch_products_paginated(limit: int | None = None) -> Generator[Dict, None, None]:
    # Public sample dataset of products, supports skip/limit pagination
    # For real sources, replace with your API or crawl implementation.
    fetched = 0
    while True:
        if limit is not None and fetched >= limit:
            break
        page_limit = min(PAGE_SIZE, (limit - fetched) if limit is not None else PAGE_SIZE)
        url = f"https://dummyjson.com/products?limit={page_limit}&skip={fetched}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            yield build_action(p)
        fetched += len(products)
        # Politeness small delay; tune per source rate limits
        time.sleep(0.05)


def streaming_actions(actions: Iterable[Dict]) -> Iterable[Dict]:
    for a in actions:
        yield a


def main() -> None:
    es = es_client()
    # Wait for ES to come up in Docker scenarios
    for i in range(30):
        try:
            if es.ping():
                break
        except Exception:
            pass
        time.sleep(1)

    ensure_index(es)

    # Temporarily optimize the index for bulk ingestion
    # We'll restore settings after bulk completes.
    original_settings = es.indices.get_settings(index=ES_INDEX).get(ES_INDEX, {}).get("settings", {}).get("index", {})
    try:
        es.indices.put_settings(index=ES_INDEX, body={
            "index": {
                "refresh_interval": "-1",
                "number_of_replicas": 0,
            }
        })
    except Exception:
        # Non-fatal in dev/local
        pass

    limit = TARGET_COUNT if TARGET_COUNT > 0 else None
    total_indexed = 0
    errors = 0

    for ok, result in helpers.streaming_bulk(
        es,
        streaming_actions(fetch_products_paginated(limit=limit)),
        chunk_size=BULK_CHUNK_SIZE,
        max_retries=BULK_MAX_RETRIES,
        initial_backoff=1,
        max_backoff=8,
        request_timeout=BULK_REQUEST_TIMEOUT,
        raise_on_error=False,
        refresh=False,
    ):
        # result is dict like {'index': {'_id': '...', 'status': 201, ...}}
        if ok:
            total_indexed += 1
        else:
            errors += 1
        if (total_indexed + errors) % 1000 == 0:
            print(f"Progress: {total_indexed} indexed, {errors} errors")

    # Restore index settings and refresh
    try:
        desired_refresh = original_settings.get("refresh_interval", "1s")
        desired_replicas = int(original_settings.get("number_of_replicas", 1))
        es.indices.put_settings(index=ES_INDEX, body={
            "index": {
                "refresh_interval": desired_refresh,
                "number_of_replicas": desired_replicas,
            }
        })
        es.indices.refresh(index=ES_INDEX)
    except Exception:
        pass

    print(f"Indexed {total_indexed} products into '{ES_INDEX}' at {ES_URL} ({errors} errors)")


if __name__ == "__main__":
    main()
