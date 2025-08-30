import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

import zstandard as zstd
from elasticsearch import Elasticsearch, helpers


ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "products")
# Path to a local .json.zst file (JSONL compressed with Zstandard)
WB_FILE = os.getenv("WB_FILE", os.path.join("data", "basket-02.json.zst"))

# Bulk tuning
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
MAX_DOCS = int(os.getenv("MAX_DOCS", "0"))  # 0 = no cap


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
                    "brand": {"type": "keyword"},
                    "ingested_at": {"type": "date"},
                    # Common extras
                    "root_category": {"type": "keyword"},
                    "color": {"type": "keyword"},
                    "vendor_code": {"type": "keyword"},
                }
            },
        },
    )


def safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace(",", "").strip()
        return float(s) if s else None
    except Exception:
        return None


def transform(row: Dict[str, Any]) -> Dict[str, Any]:
    # Known WB fields from the dataset sample:
    # - imt_id, nm_id, imt_name, subj_name, subj_root_name, nm_colors_names,
    #   vendor_code, description, brand_name, ... (prices may be absent in this file)
    title = row.get("imt_name")
    description = row.get("description")
    category = row.get("subj_name") or row.get("subj_root_name")

    # Price fields sometimes appear as priceU/salePriceU in other WB dumps (in cents). Not present here.
    price = None
    if row.get("salePriceU") is not None:
        price = safe_float(row.get("salePriceU"))
        if price is not None:
            price = price / 100.0
    elif row.get("priceU") is not None:
        price = safe_float(row.get("priceU"))
        if price is not None:
            price = price / 100.0

    # Build URL if nm_id available (WB product detail URL pattern)
    nm_id = row.get("nm_id")
    url = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx" if nm_id else None

    # Image not present in this file variant; leave None.
    image_url = None

    now_iso = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {
        "title": title,
        "description": description,
        "category": category,
        "price": price,
        "url": url,
        "image_url": image_url,
        "source": "wildberries",
        "source_id": str(nm_id or row.get("imt_id")),
        "brand": row.get("brand_name"),
        "ingested_at": now_iso,
        # Extras (kept for later analysis)
        "root_category": row.get("subj_root_name"),
        "color": row.get("nm_colors_names"),
        "vendor_code": row.get("vendor_code"),
    }
    return doc


def iter_jsonl_zst(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "rb") as fh:
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(fh) as reader:
            buf = b""
            while True:
                chunk = reader.read(262_144)
                if not chunk:
                    break
                buf += chunk
                while True:
                    nl = buf.find(b"\n")
                    if nl == -1:
                        break
                    line = buf[:nl]
                    buf = buf[nl + 1 :]
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    yield obj


def actions(rows: Iterable[Dict[str, Any]]):
    sent = 0
    for row in rows:
        doc = transform(row)
        sid = doc.get("source_id")
        if not sid:
            continue
        yield {
            "_index": ES_INDEX,
            "_id": f"wb-{sid}",
            "_op_type": "index",
            "_source": doc,
        }
        sent += 1
        if MAX_DOCS > 0 and sent >= MAX_DOCS:
            return


def verify(es: Elasticsearch) -> None:
    try:
        resp = es.count(index=ES_INDEX, body={"query": {"term": {"source": "wildberries"}}})
        print(f"Count for source=wildberries: {resp.get('count')} docs")
        sample = es.search(
            index=ES_INDEX,
            size=3,
            body={
                "query": {"term": {"source": "wildberries"}},
                "sort": [{"ingested_at": {"order": "desc", "missing": "_last"}}],
                "_source": [
                    "title",
                    "category",
                    "price",
                    "brand",
                    "color",
                    "url",
                    "source",
                    "source_id",
                ],
            },
            request_timeout=REQUEST_TIMEOUT,
        )
        for h in sample.get("hits", {}).get("hits", []):
            print("-", h.get("_source"))
    except Exception as e:
        print("Verification failed:", repr(e))


def main() -> None:
    if not os.path.exists(WB_FILE):
        raise SystemExit(f"WB file not found: {WB_FILE}")
    es = es_client()
    ensure_index(es)

    ok = 0
    failed = 0
    for success, _ in helpers.streaming_bulk(
        es,
        actions(iter_jsonl_zst(WB_FILE)),
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
