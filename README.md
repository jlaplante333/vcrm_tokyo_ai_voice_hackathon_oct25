# CRMBLR — Voice‑Driven CRM on Elasticsearch

CRMBLR is a split‑screen, voice‑first CRM builder. On the left is a chat interface; on the right is a dynamic panel where you can create and manage Elasticsearch documents on the fly. Voice is powered by OpenAI’s Realtime API over WebRTC, and server actions are invoked via custom function calls.

Core features
- Voice workspace: WebRTC to OpenAI Realtime with server‑generated ephemeral tokens.
- Dynamic CRUD: Create, read, update, and delete Elasticsearch documents without fixed schemas.
- Auth: Google Sign‑In and email/password (JWT). Protected routes for voice tokens and user info.
- Simple stack: FastAPI, Jinja2 templates, minimal JS; Elasticsearch for storage.

Quick start
1) Set environment variables (compose auto‑loads `.env`):
- `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `OPENAI_API_KEY`
- `ELASTICSEARCH_URL` (default `http://es:9200`), `ES_INDEX`, `ES_USERS_INDEX`

2) Build and run:
```
docker-compose up -d --build
```

3) Open the app:
- Login: http://localhost:8000/login (Google or email/password)
- Workspace: http://localhost:8000/ (Start Voice in the right panel)

How it works
- Backend: FastAPI serves pages and APIs (`/auth/*`, `/token`, `/me`). `/token` returns an ephemeral key for the Realtime API and requires `Authorization: Bearer <JWT>`.
- Voice: The browser creates a `RTCPeerConnection`, adds mic audio, and exchanges SDP with OpenAI using the ephemeral key to stream and receive audio.
- Data: Elasticsearch stores users and domain documents. Dynamic CRUD endpoints (and function call handlers) operate on runtime‑specified indices and documents.

Project layout
- `app/`: FastAPI app (`main.py`, `auth.py`, `search.py`, `templates/`, `static/`).
- `scraper/`: Optional ingestion utilities for sample datasets.
- Root: `docker-compose.yml`, `Dockerfile`, `requirements.txt`.

Notes
- Kibana (optional) at `http://localhost:5601` helps inspect documents.
- When mappings change, `docker-compose down -v` can reset local data.

Contributing
- See AGENTS.md for coding style, testing, and PR workflow.
