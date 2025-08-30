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
   Choose one of the following ingestion methods based on your data source:

   **Option A: Sample Data (DummyJSON API)**
   This fetches sample products from a public API. Good for testing and development.
   
   ```bash
   docker-compose run --rm scraper
   ```

   **Option B: Amazon CSV Data**
   If you have Amazon product data in CSV format, place it in the `data/` directory and run:
   
   ```bash
   docker-compose run --rm -v "$(pwd)/data:/app/data:ro" scraper python -m scraper.ingest_amazon_csv
   ```

   **Option C: Custom JSON Data**
   For custom JSON files in the `data/` directory:
   
   ```bash
   docker-compose run --rm -v "$(pwd)/data:/app/data:ro" scraper python -m scraper.ingest_from_data
   ```

   **Option D: Excel/XLSX Files**
   For Excel files in the `data/` directory:
   
   ```bash
   docker-compose run --rm -v "$(pwd)/data:/app/data:ro" scraper python -m scraper.ingest_from_xlsx
   ```

   **Note**: You only need to run ingestion once per data source. Data persists in Elasticsearch volumes across Docker restarts.

3. Access the application:
   Open your browser at:
   http://localhost:8001

   Type in the search bar to see live results.

   **Additional Services:**
   - **Kibana** (data visualization): http://localhost:5601
   - **Elasticsearch** (search API): http://localhost:9200

## Configuration

- Environment:
  - `ELASTICSEARCH_URL` (default `http://es:9200` in Docker, `http://localhost:9200` locally)
  - `ES_INDEX` (default `products`)

## Data Management

### Data Persistence
- **Elasticsearch data persists** across Docker restarts using named volumes
- **No need to re-ingest** data every time you start the application
- Data is stored in the `esdata` Docker volume

### Managing Data
- **View data**: Access Kibana at `http://localhost:5601` to inspect indexed documents
- **Clear all data**: `docker-compose down -v` (removes volumes, requires re-ingestion)
- **Restart services**: `docker-compose restart` (preserves data)
- **View logs**: `docker-compose logs -f web` or `docker-compose logs -f es`

### Ingestion Configuration
You can customize ingestion behavior with environment variables:
- `BULK_CHUNK_SIZE`: Number of documents per batch (default: 500-1000)
- `TARGET_COUNT`: Limit number of documents to ingest (default: 0 = no limit)
- `CSV_FILE`: Path to CSV file for Amazon ingestion
- `CHUNK_SIZE`: Batch size for CSV processing (default: 1000)

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
