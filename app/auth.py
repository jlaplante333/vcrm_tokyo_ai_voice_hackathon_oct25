import os
import time
from typing import Optional, Dict, Any

import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .search import es_client
import bcrypt


ALGORITHM = "HS256"


def get_secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if not key:
        raise RuntimeError("SECRET_KEY not configured")
    return key


def get_users_index_name() -> str:
    return os.getenv("ES_USERS_INDEX", "users")


def ensure_users_index():
    index = get_users_index_name()
    if not es_client.indices.exists(index=index):
        es_client.indices.create(
            index=index,
            body={
                "mappings": {
                    "properties": {
                        "email": {"type": "keyword"},
                        "name": {"type": "text"},
                        "picture": {"type": "keyword"},
                        "created_at": {"type": "date"},
                        "last_login": {"type": "date"},
                        "google_sub": {"type": "keyword"},
                        "password_hash": {"type": "keyword"},
                    }
                }
            },
        )


def issue_jwt(payload: Dict[str, Any], expires_in: int = 60 * 60 * 24) -> str:
    now = int(time.time())
    body = {
        **payload,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(body, get_secret_key(), algorithm=ALGORITHM)


def verify_jwt(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


http_bearer = HTTPBearer(auto_error=False)


def require_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)) -> Dict[str, Any]:
    if not creds or not creds.scheme.lower() == "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return verify_jwt(creds.credentials)


def upsert_user_from_google(idinfo: Dict[str, Any]) -> Dict[str, Any]:
    index = get_users_index_name()
    sub = idinfo.get("sub")
    email = idinfo.get("email")
    name = idinfo.get("name")
    picture = idinfo.get("picture")
    now = int(time.time() * 1000)

    # Prefer email as stable id when available
    doc_id = email or sub
    if not doc_id:
        raise ValueError("Missing Google user identifiers")

    # Try get existing
    try:
        existing = es_client.get(index=index, id=doc_id)
        source = existing.get("_source", {})
        source.update({
            "email": email,
            "name": name,
            "picture": picture,
            "last_login": now,
            "google_sub": sub,
        })
        es_client.index(index=index, id=doc_id, document=source, refresh="wait_for")
        return {"id": doc_id, **source}
    except Exception:
        # Create
        doc = {
            "email": email,
            "name": name,
            "picture": picture,
            "created_at": now,
            "last_login": now,
            "google_sub": sub,
        }
        es_client.index(index=index, id=doc_id, document=doc, refresh="wait_for")
        return {"id": doc_id, **doc}


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    index = get_users_index_name()
    # Try direct id lookup by email
    try:
        res = es_client.get(index=index, id=email)
        src = res.get("_source", {})
        return {"id": res.get("_id", email), **src}
    except Exception:
        pass
    # Fallback: search by email field
    try:
        res = es_client.search(index=index, body={
            "query": {"term": {"email": email}}
        }, size=1)
        hits = res.get("hits", {}).get("hits", [])
        if hits:
            h = hits[0]
            src = h.get("_source", {})
            return {"id": h.get("_id"), **src}
    except Exception:
        pass
    return None


def create_user_email(email: str, password: str, name: Optional[str] = None) -> Dict[str, Any]:
    index = get_users_index_name()
    now = int(time.time() * 1000)
    doc_id = email
    doc = {
        "email": email,
        "name": name or email.split("@")[0],
        "created_at": now,
        "last_login": now,
        "password_hash": hash_password(password),
    }
    es_client.index(index=index, id=doc_id, document=doc, refresh="wait_for")
    return {"id": doc_id, **doc}
