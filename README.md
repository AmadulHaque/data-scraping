# Wafilife.com Scraper

Async web scraper for wafilife.com (WooCommerce) book store. Discovers product URLs via sitemap + category crawling, extracts data (JSON-LD first, HTML fallback), normalizes, stores in PostgreSQL, exports JSON/JSONL.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit as needed

# Database (option A: local psql)
./scripts/setup_database.sh

# Database (option B: docker)
docker compose up -d postgres
```

Tables also auto-create via SQLAlchemy on scraper start.

## Usage

```bash
# 1. Discover product URLs (sitemap + category crawl)
python main.py discover

# 2. Scrape products
python main.py scrape --limit 100

# 3. Retry failed URLs
python main.py retry-failed

# 4. Export data (json/jsonl)
python main.py export --format jsonl

# 5. Download product images to exports/images/{slug}/
python main.py images

# 6. Last run statistics
python main.py stats

# 7. Serve REST API of all scraped data
pip install fastapi uvicorn
uvicorn api:app --port 8000
```

Or run full pipeline in Docker:

```bash
docker compose up --build
```

## Test mode

```bash
TEST_MODE=true MAX_PRODUCTS=10 python main.py scrape
```

## Structure

```
app/
├── config.py            # pydantic-settings configuration (.env)
├── crawler/
│   ├── base.py          # httpx client, retry, JSON-LD extraction, hashing
│   ├── discovery.py     # sitemap + category URL discovery
│   └── pagination.py    # ?page={n} pagination handling
├── extractors/
│   ├── product.py       # JSON-LD > HTML extraction with attribute merge
│   ├── author.py        # author pages/products
│   ├── publisher.py     # publisher pages/products
│   └── category.py      # breadcrumb/category hierarchy
├── models/
│   ├── database.py      # SQLAlchemy ORM models
│   └── pydantic_models.py  # validation schemas
├── pipelines/
│   ├── processor.py     # cleaning, discount calc, ISBN normalization
│   └── normalizer.py    # text/price/slug helpers re-export
├── storage/
│   ├── postgres.py      # repository: upserts, URL queue, runs, errors
│   └── export.py        # JSON/JSONL export
└── utils/               # logging (loguru), retry (tenacity), validators
migrations/              # raw SQL schema
```

## API

`api.py` (FastAPI) serves everything scraped. Interactive docs at `/docs`.

| Endpoint | Description |
|---|---|
| `GET /api/products` | Paginated list. Filters: `q`, `category`, `author`, `publisher`, `in_stock`, `min_price`, `max_price`, `sort` |
| `GET /api/products/{slug-or-id}` | Single product with authors, publisher, categories, images, metadata |
| `GET /api/categories` / `/authors` / `/publishers` | Reference lists |
| `GET /api/stats` | Scrape counts + last run info |
| `/images/{slug}/main.jpg` | Downloaded images (static) |

Example:

```bash
curl "localhost:8000/api/products?category=উপন্যাস&in_stock=true&sort=price_asc&per_page=50"
```

## Data flow

1. **Discovery**: sitemap.xml (+ index) → `/product/` URLs; category crawl with pagination.
2. **Queue**: URLs stored in `scrape_urls` (pending → processing → completed/failed).
3. **Extraction**: JSON-LD `Product` > WooCommerce HTML; Bengali attribute labels supported (পৃষ্ঠা, বাঁধাই, ভাষা...).
4. **Processing**: price cleanup, discount calculation, ISBN normalization, slug fallback.
5. **Storage**: upsert by external_id/url/slug; authors/publishers/categories get-or-create; images/metadata replaced on update.
6. **Export**: timestamped files in `exports/`.

## Laravel integration

`laravel-import/` contains `ProductImportController` and `ProductImportRequest`. Copy into a Laravel app, register route:

```php
Route::post('/api/products/import', [ProductImportController::class, 'import']);
```

Accepts batches of up to 500 products matching the exported JSONL schema and dispatches `ProcessProductImport` jobs.
