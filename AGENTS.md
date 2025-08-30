# Repository Guidelines

## Project Structure & Module Organization
- `app/`: FastAPI app (`main.py`, `search.py`), Jinja2 `templates/`, static assets in `static/`.
- `scraper/`: ingestion scripts (`ingest_from_data.py`, `ingest_from_xlsx.py`, `ingest_amazon_csv.py`, `simple_ingest.py`).
- Root: `Dockerfile`, `Dockerfile.scraper`, `docker-compose.yml`, `requirements.txt`, `LICENSE`.
- Tests: add under `tests/` as needed.

## Build, Test, and Development Commands
- Build & start stack: `docker-compose up -d --build` (web, Elasticsearch, Kibana).
- Seed sample JSON: `docker-compose run --rm scraper`.
- Ingest local JSON/XLSX/CSV:
  - `docker-compose run --rm -v "$(pwd)/data:/app/data:ro" scraper python -m scraper.ingest_from_data`
  - `docker-compose run --rm -v "$(pwd)/data:/app/data:ro" scraper python -m scraper.ingest_from_xlsx`
  - `docker-compose run --rm -v "$(pwd)/data:/app/data:ro" scraper python -m scraper.ingest_amazon_csv`
- Local dev (no Compose): `ELASTICSEARCH_URL=http://localhost:9200 uvicorn app.main:app --reload`.
- Logs: `docker-compose logs -f web`; stop/clean: `docker-compose down -v`.

## Coding Style & Naming Conventions
- Python 3.11, PEP 8, 4‑space indent; prefer type hints for new code.
- Names: modules/functions `snake_case`; classes `PascalCase`; constants `UPPER_SNAKE_CASE`.
- Templates: Jinja2 with small, composable partials (e.g., `_results.html`).

## Testing Guidelines
- Use `pytest` and FastAPI `TestClient`.
- Place tests in `tests/` with filenames `test_*.py`.
- Use a temporary index (e.g., `ES_INDEX=test_products`) and clean up after.

## Commit & Pull Request Guidelines
- Commits: imperative, concise, scoped (e.g., "ingest amazon csv", "widen search input").
- PRs: include what/why, run steps, screenshots for UI, and linked issues.
- Verify `docker-compose up -d` succeeds and data ingests before requesting review.

## Security & Configuration Tips
- Configure via env: `ELASTICSEARCH_URL`, `ES_INDEX`. Store secrets in `.env` (gitignored).
- Do not commit credentials or PII. Respect dataset licenses.
- When changing ES mappings, consider `docker-compose down -v` to reset local data.

## Observability & Admin
- Kibana at `http://localhost:5601`: create a data view `products` (time field `ingested_at`) to inspect documents.

