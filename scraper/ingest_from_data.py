import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from elasticsearch import Elasticsearch, helpers


ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "products")
DATA_FILE = os.getenv(
    "DATA_FILE",
    os.path.join("data", "archive", "flipkart_fashion_products_dataset.json"),
)


def es_client() -> Elasticsearch:
    return Elasticsearch([ELASTICSEARCH_URL])


def ensure_index(es: Elasticsearch) -> None:
    # Create index with minimal mapping if it does not exist
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
                    # Optional extras for later use
                    "brand": {"type": "keyword"},
                    "average_rating": {"type": "float"},
                    "out_of_stock": {"type": "boolean"},
                    "ingested_at": {"type": "date"}
                }
            },
        },
    )


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value)
        s = s.replace(",", "").strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def transform(row: Dict[str, Any]) -> Dict[str, Any]:
    # pick category preference
    category = row.get("sub_category") or row.get("category")
    price = to_float(row.get("selling_price")) or to_float(row.get("actual_price"))
    images = row.get("images") or []
    image_url = images[0] if images else None

    pid = str(row.get("pid") or row.get("_id"))
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "title": row.get("title"),
        "description": row.get("description"),
        "category": category,
        "price": price,
        "url": row.get("url"),
        "image_url": image_url,
        "source": "flipkart",
        "source_id": pid,
        # extras
        "brand": row.get("brand"),
        "average_rating": to_float(row.get("average_rating")),
        "out_of_stock": bool(row.get("out_of_stock", False)),
        "ingested_at": now_iso,
    }
    return doc


def load_rows(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def actions(rows: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for row in rows:
        doc = transform(row)
        yield {
            "_index": ES_INDEX,
            "_id": f"flipkart-{doc['source_id']}",
            "_op_type": "index",
            "_source": doc,
        }


def verify(es: Elasticsearch) -> None:
    try:
        # Count docs for this source
        resp = es.count(index=ES_INDEX, body={"query": {"term": {"source": "flipkart"}}})
        print(f"Count for source=flipkart: {resp.get('count')} docs")
        # Fetch a tiny sample to confirm fields
        sample = es.search(
            index=ES_INDEX,
            size=3,
            body={
                "query": {"term": {"source": "flipkart"}},
                "sort": [{"ingested_at": {"order": "desc"}}],
                "_source": [
                    "title",
                    "category",
                    "price",
                    "image_url",
                    "url",
                    "source",
                    "source_id",
                ],
            },
        )
        hits = sample.get("hits", {}).get("hits", [])
        for h in hits:
            print("-", h.get("_source"))
    except Exception as e:
        print("Verification failed:", repr(e))


def main() -> None:
    if not os.path.exists(DATA_FILE):
        raise SystemExit(f"Data file not found: {DATA_FILE}")

    es = es_client()
    ensure_index(es)

    rows = load_rows(DATA_FILE)
    total = len(rows)
    print(f"Loaded {total} rows from {DATA_FILE}")

    ok, failed = helpers.bulk(es, actions(rows), stats_only=True, chunk_size=1000)
    print(f"Bulk result: indexed={ok}, errors={failed}")

    verify(es)


if __name__ == "__main__":
    main()

