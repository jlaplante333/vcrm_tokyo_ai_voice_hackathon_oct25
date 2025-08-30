import os
import csv
from datetime import datetime, timezone
from typing import Dict, Any, Iterable

from elasticsearch import Elasticsearch, helpers


ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "products")
CSV_FILE = os.getenv("CSV_FILE", os.path.join("data", "amazon_products.csv"))
CATEGORIES_FILE = os.getenv("CATEGORIES_FILE", os.path.join("data", "amazon_categories.csv"))

# Bulk tuning (safe defaults)
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))


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
                    "ingested_at": {"type": "date"}
                }
            },
        },
    )


def load_categories(path: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not os.path.exists(path):
        return mapping
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            cid = str(row.get("id") or "").strip()
            name = (row.get("category_name") or "").strip()
            if cid:
                mapping[cid] = name
    return mapping


def transform(row: Dict[str, Any], categories: Dict[str, str]) -> Dict[str, Any]:
    asin = (row.get("asin") or "").strip()
    title = row.get("title")
    url = row.get("productURL")
    image_url = row.get("imgUrl")
    price = row.get("price")
    try:
        price_f = float(price) if price not in (None, "", "0.0", "0") else None
    except Exception:
        price_f = None
    category_id = str(row.get("category_id") or "").strip()
    category_name = categories.get(category_id) if category_id else None
    stars = row.get("stars")
    try:
        stars_f = float(stars) if stars not in (None, "") else None
    except Exception:
        stars_f = None
    reviews = row.get("reviews")
    try:
        reviews_i = int(float(reviews)) if reviews not in (None, "") else None
    except Exception:
        reviews_i = None

    doc: Dict[str, Any] = {
        "title": title,
        "description": None,
        "category": category_name,
        "price": price_f,
        "url": url,
        "image_url": image_url,
        "source": "amazon",
        "source_id": asin,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        # Keep extras under their names; ES will dynamically map
        "category_id": category_id or None,
        "stars": stars_f,
        "reviews": reviews_i,
    }
    return doc


def iter_csv_rows(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            yield row


def actions(rows: Iterable[Dict[str, Any]], categories: Dict[str, str]):
    for row in rows:
        asin = (row.get("asin") or "").strip()
        if not asin:
            continue
        doc = transform(row, categories)
        yield {
            "_index": ES_INDEX,
            "_id": f"amazon-{asin}",
            "_op_type": "index",
            "_source": doc,
        }


def verify(es: Elasticsearch) -> None:
    # Count amazon docs and show a small sample
    resp = es.count(index=ES_INDEX, body={"query": {"term": {"source": "amazon"}}})
    print(f"Count for source=amazon: {resp.get('count')} docs")
    sample = es.search(
        index=ES_INDEX,
        size=3,
        body={
            "query": {"term": {"source": "amazon"}},
            "sort": [{"ingested_at": {"order": "desc", "missing": "_last"}}],
            "_source": ["title", "category", "price", "image_url", "url", "source", "source_id"],
        },
        request_timeout=REQUEST_TIMEOUT,
    )
    for h in sample.get("hits", {}).get("hits", []):
        print("-", h.get("_source"))


def main() -> None:
    if not os.path.exists(CSV_FILE):
        raise SystemExit(f"CSV file not found: {CSV_FILE}")
    es = es_client()
    ensure_index(es)

    categories = load_categories(CATEGORIES_FILE)
    print(f"Loaded {len(categories)} categories from {CATEGORIES_FILE}")

    ok = 0
    failed = 0
    for success, _ in helpers.streaming_bulk(
        es,
        actions(iter_csv_rows(CSV_FILE), categories),
        chunk_size=CHUNK_SIZE,
        request_timeout=REQUEST_TIMEOUT,
        max_retries=3,
        initial_backoff=1,
        max_backoff=8,
        refresh=False,
        raise_on_error=False,
    ):
        if success:
            ok += 1
        else:
            failed += 1
        if (ok + failed) % 5000 == 0:
            print(f"Progress: {ok} indexed, {failed} errors")

    es.indices.refresh(index=ES_INDEX)
    print(f"Bulk result: indexed={ok}, errors={failed}")
    verify(es)


if __name__ == "__main__":
    main()

