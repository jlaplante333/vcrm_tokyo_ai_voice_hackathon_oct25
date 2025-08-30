import os
from typing import List, Dict, Any
import time
from elasticsearch.exceptions import ConnectionError as ESConnectionError
from elasticsearch import Elasticsearch, helpers


def get_es_url() -> str:
    return os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")


def get_index_name() -> str:
    return os.getenv("ES_INDEX", "products")


es_client = Elasticsearch([get_es_url()])


def wait_for_es(max_attempts: int = 60, delay_seconds: float = 1.0) -> bool:
    for _ in range(max_attempts):
        try:
            if es_client.ping():
                return True
        except Exception:
            pass
        time.sleep(delay_seconds)
    return False


def ensure_index() -> None:
    # Ensure ES is reachable first; avoid crashing on startup race
    wait_for_es()
    index = get_index_name()
    try:
        if es_client.indices.exists(index=index):
            return
        es_client.indices.create(
            index=index,
            body={
                "settings": {
                    "analysis": {
                        "analyzer": {
                            "default": {"type": "standard"},
                            "english": {"type": "standard"}
                        }
                    }
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
                        "source_id": {"type": "keyword"},
                        "ingested_at": {"type": "date"}
                    }
                },
            },
        )
    except ESConnectionError:
        # Swallow transient connection errors; app can proceed and queries will retry
        pass


def search_products(query: str, size: int = 200) -> List[Dict[str, Any]]:
    index = get_index_name()
    response = es_client.search(
        index=index,
        body={
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title^3",
                        "description",
                        "category^2"
                    ],
                    "type": "best_fields",
                    "operator": "and",
                    "fuzziness": "AUTO"
                }
            },
            "size": size
        },
    )
    hits = [
        {
            "id": h.get("_id"),
            **h.get("_source", {})
        }
        for h in response.get("hits", {}).get("hits", [])
    ]
    return hits


def recent_products(size: int = 200) -> List[Dict[str, Any]]:
    index = get_index_name()
    response = es_client.search(
        index=index,
        body={
            "query": {"match_all": {}},
            "sort": [
                {"ingested_at": {"order": "desc", "missing": "_last"}},
                {"_id": {"order": "desc"}}
            ],
            "size": size,
        },
    )
    hits = [
        {"id": h.get("_id"), **h.get("_source", {})}
        for h in response.get("hits", {}).get("hits", [])
    ]
    return hits
