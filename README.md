# nibbins

A simple, fast, full-stack product search application built with FastAPI, HTMX, and Elasticsearch.

This project demonstrates a modern, minimal web app that avoids a heavy frontend by leveraging server-side rendering with HTMX and full‑text search via Elasticsearch.

## Technology Stack

- Backend: FastAPI (Python)
- Frontend: HTMX with Jinja2 templates
- Search: Elasticsearch (single-node in Docker)
- Containerization: Docker & Docker Compose
- Data Population: Python scraper using `requests` and Elasticsearch bulk indexing

## How to Run the Application

1. Start the services:
   This command builds the images and starts the FastAPI backend and Elasticsearch.

   ```bash
   docker-compose up -d --build
   ```

2. Populate the index:
   This command runs the scraper to fetch sample product data and index it into Elasticsearch. You only need to run this once (re-run to refresh data).

   ```bash
   docker-compose run --rm scraper
   ```

3. Access the application:
   Open your browser at:
   http://localhost:8000

   Type in the search bar to see live results.

## Configuration

- Environment:
  - `ELASTICSEARCH_URL` (default `http://es:9200` in Docker, `http://localhost:9200` locally)
  - `ES_INDEX` (default `products`)

## Future Implementation Plans

This prototype can be extended with several features:

- Improved Search Experience:
  - Pagination for large result sets
  - Sorting (price, relevance)
  - Filtering (e.g., by category)

- Enhanced Scraper:
  - Multiple data sources
  - Better error handling and logging
  - Scheduling for freshness
  - Incremental updates and deduplication

- Production-Ready Deployment:
  - Reverse proxy (Traefik/Nginx) and SSL
  - Elasticsearch scaling if data/traffic demands
  - Robust deployment strategy (e.g., Kubernetes) if needed

- User Features:
  - Authentication
  - Saved searches and favorites

## Data Sources

This project uses publicly available datasets for demonstration and testing purposes. Please review and comply with each dataset's license and terms of use before redistributing or using the data commercially.

- Amazon Products Dataset 2023 (1.4M products): https://www.kaggle.com/datasets/asaniczka/amazon-products-dataset-2023-1-4m-products
- Amazon UK Products Dataset 2023: https://www.kaggle.com/datasets/asaniczka/amazon-uk-products-dataset-2023
