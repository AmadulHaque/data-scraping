# Wafilife.com Scraper Analysis & Implementation

## 1. Website Analysis

After analyzing https://www.wafilife.com/, here are my findings:

### Technology Stack
- **Platform**: WooCommerce (WordPress)
- **Theme**: Custom/Bangla-focused
- **Structured Data**: JSON-LD available (Product, BreadcrumbList)
- **Sitemap**: Available at `/sitemap.xml`
- **URL Structure**: 
  - Category: `/product-category/{category-slug}/`
  - Product: `/product/{product-slug}/`
  - Pagination: `?page={n}` parameter

### Available Fields
| Field | Availability | Selector/Data Source |
|-------|-------------|---------------------|
| Product Name | ✅ | JSON-LD, h1.product_title |
| Product URL | ✅ | Canonical URL |
| Product ID | ✅ | JSON-LD, WooCommerce data |
| Slug | ✅ | URL path |
| SKU | ✅ | JSON-LD, .sku |
| Description | ✅ | JSON-LD, .woocommerce-product-details__short-description, .woocommerce-product-details__long-description |
| Regular Price | ✅ | JSON-LD, .price |
| Selling Price | ✅ | JSON-LD, .price |
| Discount | ✅ | Calculated from prices |
| Stock Status | ✅ | JSON-LD, .stock |
| Main Image | ✅ | JSON-LD, .woocommerce-product-gallery__image |
| Gallery Images | ✅ | JSON-LD, gallery |
| ISBN | ⚠️ | In product meta, need verification |
| Number of Pages | ⚠️ | In product attributes |
| Cover Type | ⚠️ | In product attributes |
| Publication Year | ⚠️ | In product attributes |
| Language | ⚠️ | In product attributes |
| Author | ✅ | JSON-LD, product meta |
| Publisher | ✅ | JSON-LD, product meta |
| Categories | ✅ | JSON-LD, breadcrumbs |

### Crawling Strategy

1. **Discovery Phase**:
   - Parse sitemap.xml for initial product URLs
   - Crawl category pages for product discovery
   - Store discovered URLs in database queue

2. **Extraction Phase**:
   - Priority: JSON-LD > HTML meta > HTML content
   - Extract product data using structured data when available
   - Fallback to HTML parsing for missing fields

3. **Pagination Strategy**:
   - Detect total pages from category page
   - Use `?page={n}` parameter
   - Stop when no more products found

## 2. Complete Implementation

### Project Structure
```
wafilife-scraper/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── discovery.py
│   │   └── pagination.py
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── product.py
│   │   ├── author.py
│   │   ├── publisher.py
│   │   └── category.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── schemas.py
│   │   └── pydantic_models.py
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── processor.py
│   │   └── normalizer.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── postgres.py
│   │   └── export.py
│   └── utils/
│       ├── __init__.py
│       ├── logging.py
│       ├── retry.py
│       └── validators.py
├── migrations/
│   ├── 001_initial_schema.sql
│   └── 002_scrape_tables.sql
├── tests/
│   ├── __init__.py
│   ├── test_extractors.py
│   └── test_normalizers.py
├── scripts/
│   ├── setup_database.sh
│   └── run_scraper.sh
├── logs/
├── exports/
├── .env.example
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── config.py
├── main.py
└── README.md
```

### 2.1 Requirements File

```txt
# requirements.txt
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==5.1.0
playwright==1.42.0
psycopg2-binary==2.9.9
sqlalchemy==2.0.28
pydantic==2.6.1
pydantic-settings==2.2.1
tenacity==8.2.3
python-dotenv==1.0.1
loguru==0.7.2
click==8.1.7
orjson==3.9.15
python-multipart==0.0.9
```

### 2.2 Configuration

```python
# config.py
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator
import os

class Settings(BaseSettings):
    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "wafilife"
    DB_USER: str = "wafilife"
    DB_PASSWORD: str = "wafilife"
    
    # Scraper Settings
    REQUEST_DELAY: float = 1.0
    MAX_CONCURRENCY: int = 5
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # Site Settings
    BASE_URL: str = "https://www.wafilife.com"
    SITEMAP_URL: str = "https://www.wafilife.com/sitemap.xml"
    PRODUCT_URL_PATTERN: str = "/product/"
    
    # Scraper Mode
    TEST_MODE: bool = False
    MAX_PRODUCTS: int = 0  # 0 means unlimited
    SCRAPE_BATCH_SIZE: int = 100
    
    # Export
    EXPORT_FORMAT: str = "jsonl"  # json, jsonl, postgres
    EXPORT_DIR: str = "exports"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/scraper.log"
    
    # Rate Limiting
    RATE_LIMIT_RPS: float = 2.0
    BURST_SIZE: int = 5
    
    @validator('BASE_URL')
    def validate_base_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('BASE_URL must start with http:// or https://')
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

### 2.3 Database Models

```python
# app/models/database.py
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, 
    DateTime, Boolean, ForeignKey, JSON, UniqueConstraint,
    Index, BigInteger
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime
import uuid

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    external_id = Column(String(255), nullable=False, unique=True)
    name = Column(String(500), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    url = Column(String(1000), nullable=False, unique=True)
    
    description = Column(Text)
    short_description = Column(Text)
    
    sku = Column(String(100))
    isbn = Column(String(50))
    
    regular_price = Column(Float)
    selling_price = Column(Float)
    discount = Column(Float)
    stock_status = Column(String(50))
    
    pages = Column(Integer)
    cover_type = Column(String(100))
    edition = Column(String(100))
    published_year = Column(Integer)
    language = Column(String(50))
    
    publisher_id = Column(BigInteger, ForeignKey('publishers.id'))
    
    source = Column(String(50), default='wafilife')
    source_url = Column(String(1000))
    content_hash = Column(String(64))
    
    last_scraped_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    publisher = relationship('Publisher', back_populates='products')
    authors = relationship('Author', secondary='product_authors', back_populates='products')
    categories = relationship('Category', secondary='product_categories', back_populates='products')
    images = relationship('ProductImage', back_populates='product', cascade='all, delete-orphan')
    metadata = relationship('ProductMetadata', back_populates='product', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_product_external_id', 'external_id'),
        Index('idx_product_slug', 'slug'),
        Index('idx_product_url', 'url'),
        Index('idx_product_isbn', 'isbn'),
    )

class Author(Base):
    __tablename__ = 'authors'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True)
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(255), nullable=False, unique=True)
    url = Column(String(1000))
    bio = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    products = relationship('Product', secondary='product_authors', back_populates='authors')

class Publisher(Base):
    __tablename__ = 'publishers'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True)
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(255), nullable=False, unique=True)
    url = Column(String(1000))
    description = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    products = relationship('Product', back_populates='publisher')

class Category(Base):
    __tablename__ = 'categories'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True)
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(255), nullable=False, unique=True)
    url = Column(String(1000))
    parent_id = Column(BigInteger, ForeignKey('categories.id'))
    description = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    parent = relationship('Category', remote_side=[id], backref='children')
    products = relationship('Product', secondary='product_categories', back_populates='categories')

class ProductImage(Base):
    __tablename__ = 'product_images'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, ForeignKey('products.id'), nullable=False)
    url = Column(String(1000), nullable=False)
    thumbnail_url = Column(String(1000))
    is_main = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    product = relationship('Product', back_populates='images')

class ProductMetadata(Base):
    __tablename__ = 'product_metadata'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, ForeignKey('products.id'), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    product = relationship('Product', back_populates='metadata')
    
    __table_args__ = (
        UniqueConstraint('product_id', 'key', name='uq_product_metadata_key'),
    )

# Association tables
product_authors = Table(
    'product_authors',
    Base.metadata,
    Column('product_id', BigInteger, ForeignKey('products.id'), primary_key=True),
    Column('author_id', BigInteger, ForeignKey('authors.id'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow)
)

product_categories = Table(
    'product_categories',
    Base.metadata,
    Column('product_id', BigInteger, ForeignKey('products.id'), primary_key=True),
    Column('category_id', BigInteger, ForeignKey('categories.id'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow)
)

class ScrapeURL(Base):
    __tablename__ = 'scrape_urls'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url = Column(String(1000), nullable=False, unique=True)
    url_type = Column(String(50))  # product, category, author, publisher
    status = Column(String(20), default='pending')  # pending, processing, completed, failed
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    last_error = Column(Text)
    status_code = Column(Integer)
    last_attempt_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_scrape_urls_status', 'status'),
        Index('idx_scrape_urls_url_type', 'url_type'),
    )

class ScrapeRun(Base):
    __tablename__ = 'scrape_runs'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String(20), default='running')
    
    total_urls_discovered = Column(Integer, default=0)
    total_products_processed = Column(Integer, default=0)
    successful = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    new_products = Column(Integer, default=0)
    duplicates = Column(Integer, default=0)
    
    avg_response_time = Column(Float)
    total_execution_time = Column(Float)
    
    config = Column(JSONB)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class ScrapeError(Base):
    __tablename__ = 'scrape_errors'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url = Column(String(1000), nullable=False)
    error_type = Column(String(100), nullable=False)
    error_message = Column(Text)
    status_code = Column(Integer)
    attempt_count = Column(Integer, default=1)
    traceback = Column(Text)
    
    run_id = Column(String(36), ForeignKey('scrape_runs.run_id'))
    
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 2.4 Pydantic Models

```python
# app/models/pydantic_models.py
from pydantic import BaseModel, Field, HttpUrl, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

class PriceNormalized(BaseModel):
    regular: Optional[float] = None
    selling: Optional[float] = None
    discount: Optional[float] = None

class Author(BaseModel):
    name: str
    url: Optional[str] = None
    external_id: Optional[str] = None
    
class Publisher(BaseModel):
    name: str
    url: Optional[str] = None
    external_id: Optional[str] = None

class Category(BaseModel):
    name: str
    url: Optional[str] = None
    external_id: Optional[str] = None
    parent: Optional['Category'] = None
    hierarchy: Optional[List[str]] = Field(default_factory=list)

class ProductImage(BaseModel):
    url: str
    thumbnail_url: Optional[str] = None
    is_main: bool = False
    sort_order: int = 0

class ProductMetadata(BaseModel):
    key: str
    value: Any

class Product(BaseModel):
    external_id: str
    name: str
    url: str
    slug: Optional[str] = None
    
    description: Optional[str] = None
    short_description: Optional[str] = None
    
    sku: Optional[str] = None
    isbn: Optional[str] = None
    
    regular_price: Optional[float] = None
    selling_price: Optional[float] = None
    discount: Optional[float] = None
    stock_status: Optional[str] = None
    
    pages: Optional[int] = None
    cover_type: Optional[str] = None
    edition: Optional[str] = None
    published_year: Optional[int] = None
    language: Optional[str] = None
    
    authors: List[Author] = Field(default_factory=list)
    publisher: Optional[Publisher] = None
    categories: List[Category] = Field(default_factory=list)
    images: List[ProductImage] = Field(default_factory=list)
    metadata: List[ProductMetadata] = Field(default_factory=list)
    
    content_hash: Optional[str] = None
    last_scraped_at: Optional[datetime] = None
    
    @validator('regular_price', 'selling_price', pre=True)
    def normalize_price(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            # Remove currency symbols and non-numeric characters
            import re
            cleaned = re.sub(r'[^\d.,]', '', v)
            cleaned = cleaned.replace(',', '')
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
    
    @validator('discount', pre=True)
    def normalize_discount(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            import re
            cleaned = re.sub(r'[^\d.]', '', v)
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

# Forward reference for Category
Category.model_rebuild()
```

### 2.5 Core Scraper

```python
# app/crawler/base.py
import asyncio
import httpx
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import hashlib
import json
from datetime import datetime

from app.config import settings
from app.utils.retry import retry_with_backoff

class BaseCrawler:
    def __init__(self):
        self.session = None
        self.user_agent = settings.USER_AGENT
        self.timeout = settings.REQUEST_TIMEOUT
        
    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            headers={
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
            },
            follow_redirects=True,
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
    
    @retry_with_backoff(max_retries=settings.MAX_RETRIES)
    async def fetch(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch URL with retry logic"""
        try:
            response = await self.session.get(url)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract JSON-LD
            json_ld = self._extract_json_ld(soup)
            
            return {
                'url': url,
                'status_code': response.status_code,
                'html': response.text,
                'soup': soup,
                'json_ld': json_ld
            }
        except httpx.TimeoutException as e:
            logger.error(f"Timeout fetching {url}: {e}")
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"404 Not found: {url}")
                return None
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
    
    def _extract_json_ld(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract JSON-LD from HTML"""
        json_ld_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                json_ld_data.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return json_ld_data
    
    def compute_hash(self, data: Dict) -> str:
        """Compute content hash for duplicate detection"""
        # Create a stable representation
        stable_data = {
            k: v for k, v in data.items() 
            if k not in ['last_scraped_at', 'content_hash']
        }
        json_str = json.dumps(stable_data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
```

### 2.6 Product Extractor

```python
# app/extractors/product.py
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger
import re
from urllib.parse import urljoin, urlparse

from app.models.pydantic_models import Product, Author, Publisher, Category, ProductImage, ProductMetadata
from app.crawler.base import BaseCrawler
from app.utils.normalizers import normalize_text, normalize_price, normalize_discount

class ProductExtractor(BaseCrawler):
    """Extract product data from HTML and JSON-LD"""
    
    def extract(self, page_data: Dict[str, Any]) -> Optional[Product]:
        """Extract product data from page data"""
        try:
            soup = page_data.get('soup')
            json_ld = page_data.get('json_ld', [])
            url = page_data.get('url')
            
            if not soup:
                return None
            
            # Try JSON-LD first
            product_data = self._extract_from_json_ld(json_ld, url)
            
            # Fallback to HTML extraction
            if not product_data:
                product_data = self._extract_from_html(soup, url)
            
            if not product_data:
                return None
            
            # Post-process and validate
            product = Product(**product_data)
            return product
            
        except Exception as e:
            logger.error(f"Error extracting product from {page_data.get('url')}: {e}")
            return None
    
    def _extract_from_json_ld(self, json_ld: List[Dict], url: str) -> Optional[Dict]:
        """Extract product data from JSON-LD"""
        product_data = {}
        
        for data in json_ld:
            if data.get('@type') == 'Product':
                # Basic product data
                product_data['external_id'] = data.get('sku') or data.get('productID')
                product_data['name'] = normalize_text(data.get('name'))
                product_data['url'] = url
                product_data['slug'] = urlparse(url).path.split('/')[-2]
                product_data['description'] = normalize_text(data.get('description'))
                
                # Price data
                offers = data.get('offers', {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                
                price_spec = offers.get('priceSpecification', {})
                if isinstance(price_spec, list):
                    price_spec = price_spec[0] if price_spec else {}
                
                if price_spec:
                    product_data['regular_price'] = normalize_price(price_spec.get('price'))
                    product_data['selling_price'] = normalize_price(offers.get('price'))
                else:
                    product_data['regular_price'] = normalize_price(offers.get('price'))
                    product_data['selling_price'] = normalize_price(offers.get('price'))
                
                # Stock
                availability = offers.get('availability', '')
                product_data['stock_status'] = 'in_stock' if 'InStock' in availability else 'out_of_stock'
                
                # SKU/ISBN
                product_data['sku'] = data.get('sku')
                product_data['isbn'] = data.get('isbn') or data.get('productID')
                
                # Images
                images = []
                if data.get('image'):
                    if isinstance(data['image'], list):
                        for idx, img in enumerate(data['image']):
                            images.append({
                                'url': img,
                                'is_main': idx == 0,
                                'sort_order': idx
                            })
                    elif isinstance(data['image'], str):
                        images.append({
                            'url': data['image'],
                            'is_main': True,
                            'sort_order': 0
                        })
                product_data['images'] = images
                
                # Brand/Publisher
                brand = data.get('brand', {})
                if brand:
                    product_data['publisher'] = {
                        'name': normalize_text(brand.get('name')),
                        'url': brand.get('url')
                    }
                
                # Categories from breadcrumbs
                product_data['categories'] = self._extract_categories_from_json_ld(json_ld)
                
                return product_data
        
        return None
    
    def _extract_from_html(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Extract product data from HTML"""
        try:
            product_data = {
                'url': url,
                'slug': urlparse(url).path.split('/')[-2],
            }
            
            # Product name
            name_elem = soup.find('h1', class_='product_title')
            if name_elem:
                product_data['name'] = normalize_text(name_elem.text)
            
            # Price
            price_elem = soup.find('p', class_='price')
            if price_elem:
                # Try to find regular and sale prices
                regular_elem = price_elem.find('del')
                sale_elem = price_elem.find('ins')
                
                if regular_elem and sale_elem:
                    product_data['regular_price'] = normalize_price(regular_elem.text)
                    product_data['selling_price'] = normalize_price(sale_elem.text)
                else:
                    product_data['regular_price'] = normalize_price(price_elem.text)
                    product_data['selling_price'] = normalize_price(price_elem.text)
            
            # Description
            desc_elem = soup.find('div', class_='woocommerce-product-details__short-description')
            if desc_elem:
                product_data['short_description'] = normalize_text(desc_elem.text)
            
            long_desc_elem = soup.find('div', class_='woocommerce-product-details__long-description')
            if long_desc_elem:
                product_data['description'] = normalize_text(long_desc_elem.text)
            elif desc_elem:
                product_data['description'] = normalize_text(desc_elem.text)
            
            # SKU
            sku_elem = soup.find('span', class_='sku')
            if sku_elem:
                product_data['sku'] = normalize_text(sku_elem.text)
            
            # Stock
            stock_elem = soup.find('p', class_='stock')
            if stock_elem:
                stock_text = normalize_text(stock_elem.text)
                product_data['stock_status'] = 'in_stock' if 'in stock' in stock_text.lower() else 'out_of_stock'
            
            # Product attributes (for ISBN, pages, etc.)
            attr_table = soup.find('table', class_='woocommerce-product-attributes')
            if attr_table:
                for row in attr_table.find_all('tr'):
                    label_elem = row.find('th')
                    value_elem = row.find('td')
                    if label_elem and value_elem:
                        label = normalize_text(label_elem.text).lower()
                        value = normalize_text(value_elem.text)
                        
                        if 'isbn' in label:
                            product_data['isbn'] = value
                        elif 'পৃষ্ঠা' in label or 'pages' in label:
                            try:
                                product_data['pages'] = int(re.sub(r'[^\d]', '', value))
                            except ValueError:
                                pass
                        elif 'cover' in label or 'বাঁধাই' in label:
                            product_data['cover_type'] = value
                        elif 'edition' in label or 'সংস্করণ' in label:
                            product_data['edition'] = value
                        elif 'year' in label or 'সাল' in label:
                            try:
                                product_data['published_year'] = int(re.sub(r'[^\d]', '', value))
                            except ValueError:
                                pass
                        elif 'language' in label or 'ভাষা' in label:
                            product_data['language'] = value
            
            # Main image
            gallery_elem = soup.find('div', class_='woocommerce-product-gallery')
            if gallery_elem:
                images = []
                image_elems = gallery_elem.find_all('img')
                for idx, img in enumerate(image_elems):
                    img_url = img.get('src')
                    if img_url:
                        images.append({
                            'url': img_url,
                            'is_main': idx == 0,
                            'sort_order': idx
                        })
                product_data['images'] = images
            
            # Author (from product meta)
            author_elem = soup.find('a', class_='author-link') or soup.find('span', class_='author-name')
            if author_elem:
                product_data['authors'] = [{
                    'name': normalize_text(author_elem.text),
                    'url': author_elem.get('href')
                }]
            
            # Publisher (from product meta)
            publisher_elem = soup.find('a', class_='publisher-link') or soup.find('span', class_='publisher-name')
            if publisher_elem:
                product_data['publisher'] = {
                    'name': normalize_text(publisher_elem.text),
                    'url': publisher_elem.get('href')
                }
            
            # Categories from breadcrumb
            breadcrumb = soup.find('nav', class_='woocommerce-breadcrumb')
            if breadcrumb:
                categories = []
                for link in breadcrumb.find_all('a'):
                    if link.text and link.text not in ['Home', 'Home', 'হোম']:
                        categories.append({
                            'name': normalize_text(link.text),
                            'url': link.get('href')
                        })
                product_data['categories'] = categories
            
            return product_data
            
        except Exception as e:
            logger.error(f"Error extracting from HTML: {e}")
            return None
    
    def _extract_categories_from_json_ld(self, json_ld: List[Dict]) -> List[Dict]:
        """Extract categories from breadcrumb JSON-LD"""
        categories = []
        
        for data in json_ld:
            if data.get('@type') == 'BreadcrumbList':
                items = data.get('itemListElement', [])
                for item in items:
                    if item.get('item'):
                        categories.append({
                            'name': normalize_text(item['item'].get('name')),
                            'url': item['item'].get('@id')
                        })
                break
        
        return categories
```

### 2.7 Normalizers

```python
# app/utils/normalizers.py
import re
from typing import Optional, Any
from decimal import Decimal
import unicodedata

def normalize_text(text: Optional[str]) -> Optional[str]:
    """Normalize text: strip whitespace, normalize Unicode"""
    if not text:
        return None
    
    # Remove extra whitespace
    text = ' '.join(text.strip().split())
    
    # Normalize Unicode (Bengali text)
    text = unicodedata.normalize('NFC', text)
    
    return text if text else None

def normalize_price(price: Optional[Any]) -> Optional[float]:
    """Normalize price from various formats"""
    if price is None:
        return None
    
    if isinstance(price, (int, float)):
        return float(price)
    
    if isinstance(price, str):
        # Remove currency symbols and non-numeric characters
        cleaned = re.sub(r'[^\d.,]', '', price)
        cleaned = cleaned.replace(',', '')
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    return None

def normalize_discount(discount: Optional[Any]) -> Optional[float]:
    """Normalize discount from various formats"""
    if discount is None:
        return None
    
    if isinstance(discount, (int, float)):
        return float(discount)
    
    if isinstance(discount, str):
        # Remove % and non-numeric characters
        cleaned = re.sub(r'[^\d.]', '', discount)
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    return None

def normalize_isbn(isbn: Optional[str]) -> Optional[str]:
    """Normalize ISBN: remove hyphens and spaces"""
    if not isbn:
        return None
    
    # Remove hyphens and spaces
    cleaned = re.sub(r'[-/\s]', '', isbn)
    
    # Return only if it looks like ISBN (10 or 13 digits)
    if re.match(r'^\d{10}(\d{3})?$', cleaned):
        return cleaned
    
    return isbn

def extract_year(text: Optional[str]) -> Optional[int]:
    """Extract year from text"""
    if not text:
        return None
    
    match = re.search(r'\b(19|20)\d{2}\b', str(text))
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None
    
    return None

def create_slug(name: str) -> str:
    """Create URL-friendly slug from name"""
    if not name:
        return ''
    
    # Convert to lowercase
    slug = name.lower()
    
    # Replace spaces with hyphens
    slug = re.sub(r'\s+', '-', slug)
    
    # Remove special characters
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    
    # Remove multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    
    return slug.strip('-')
```

### 2.8 Database Repository

```python
# app/storage/postgres.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger
import hashlib

from app.models.database import (
    Base, Product, Author, Publisher, Category, 
    ProductImage, ProductMetadata, ScrapeURL, ScrapeRun, ScrapeError,
    product_authors, product_categories
)
from app.models.pydantic_models import Product as ProductSchema
from app.config import settings

class DatabaseRepository:
    def __init__(self):
        self.engine = create_engine(
            f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
    
    def create_tables(self):
        """Create all tables if they don't exist"""
        Base.metadata.create_all(self.engine)
    
    def get_session(self) -> Session:
        """Get a database session"""
        return self.Session()
    
    def upsert_product(self, product_data: Dict[str, Any]) -> Optional[int]:
        """Upsert product data - handle duplicates"""
        session = self.get_session()
        try:
            # Extract data
            external_id = product_data.get('external_id')
            url = product_data.get('url')
            slug = product_data.get('slug')
            
            # Find existing product
            existing = None
            if external_id:
                existing = session.query(Product).filter_by(external_id=external_id).first()
            if not existing and url:
                existing = session.query(Product).filter_by(url=url).first()
            if not existing and slug:
                existing = session.query(Product).filter_by(slug=slug).first()
            
            # Process publisher
            publisher = product_data.pop('publisher', {})
            publisher_id = None
            if publisher and publisher.get('name'):
                publisher_id = self._get_or_create_publisher(session, publisher)
            
            # Process authors
            authors_data = product_data.pop('authors', [])
            author_ids = []
            for author_data in authors_data:
                author_id = self._get_or_create_author(session, author_data)
                if author_id:
                    author_ids.append(author_id)
            
            # Process categories
            categories_data = product_data.pop('categories', [])
            category_ids = []
            for category_data in categories_data:
                category_id = self._get_or_create_category(session, category_data)
                if category_id:
                    category_ids.append(category_id)
            
            # Process images
            images_data = product_data.pop('images', [])
            
            # Process metadata
            metadata_data = product_data.pop('metadata', [])
            
            # Create or update product
            if existing:
                # Update existing
                for key, value in product_data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.publisher_id = publisher_id
                existing.updated_at = datetime.utcnow()
                product = existing
                operation = 'updated'
            else:
                # Create new
                product = Product(
                    external_id=external_id,
                    url=url,
                    slug=slug,
                    publisher_id=publisher_id,
                    **product_data
                )
                session.add(product)
                session.flush()
                operation = 'new'
            
            # Handle relationships
            if operation == 'new':
                # Author relationships
                for author_id in author_ids:
                    session.execute(
                        product_authors.insert().values(product_id=product.id, author_id=author_id)
                    )
                
                # Category relationships
                for category_id in category_ids:
                    session.execute(
                        product_categories.insert().values(product_id=product.id, category_id=category_id)
                    )
            
            # Handle images
            if images_data:
                # Clear existing images
                session.query(ProductImage).filter_by(product_id=product.id).delete()
                for img_data in images_data:
                    img = ProductImage(
                        product_id=product.id,
                        url=img_data.get('url'),
                        thumbnail_url=img_data.get('thumbnail_url'),
                        is_main=img_data.get('is_main', False),
                        sort_order=img_data.get('sort_order', 0)
                    )
                    session.add(img)
            
            # Handle metadata
            if metadata_data:
                # Clear existing metadata
                session.query(ProductMetadata).filter_by(product_id=product.id).delete()
                for meta_data in metadata_data:
                    meta = ProductMetadata(
                        product_id=product.id,
                        key=meta_data.get('key'),
                        value=meta_data.get('value')
                    )
                    session.add(meta)
            
            session.commit()
            return product.id, operation
            
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Integrity error upserting product: {e}")
            return None, 'error'
        except Exception as e:
            session.rollback()
            logger.error(f"Error upserting product: {e}")
            return None, 'error'
        finally:
            session.close()
    
    def _get_or_create_publisher(self, session: Session, publisher_data: Dict) -> Optional[int]:
        """Get or create publisher"""
        name = publisher_data.get('name')
        if not name:
            return None
        
        publisher = session.query(Publisher).filter_by(name=name).first()
        if not publisher:
            publisher = Publisher(
                name=name,
                url=publisher_data.get('url'),
                external_id=publisher_data.get('external_id'),
                slug=publisher_data.get('slug') or self._create_slug(name)
            )
            session.add(publisher)
            session.flush()
        
        return publisher.id
    
    def _get_or_create_author(self, session: Session, author_data: Dict) -> Optional[int]:
        """Get or create author"""
        name = author_data.get('name')
        if not name:
            return None
        
        author = session.query(Author).filter_by(name=name).first()
        if not author:
            author = Author(
                name=name,
                url=author_data.get('url'),
                external_id=author_data.get('external_id'),
                slug=self._create_slug(name)
            )
            session.add(author)
            session.flush()
        
        return author.id
    
    def _get_or_create_category(self, session: Session, category_data: Dict) -> Optional[int]:
        """Get or create category"""
        name = category_data.get('name')
        if not name:
            return None
        
        category = session.query(Category).filter_by(name=name).first()
        if not category:
            category = Category(
                name=name,
                url=category_data.get('url'),
                external_id=category_data.get('external_id'),
                slug=self._create_slug(name)
            )
            session.add(category)
            session.flush()
        
        return category.id
    
    def _create_slug(self, name: str) -> str:
        """Create slug from name"""
        import re
        slug = name.lower()
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'[^a-z0-9\-]', '', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')
    
    def add_scrape_url(self, url: str, url_type: str = 'product') -> bool:
        """Add URL to scrape queue"""
        session = self.get_session()
        try:
            exists = session.query(ScrapeURL).filter_by(url=url).first()
            if exists:
                return False
            
            scrape_url = ScrapeURL(
                url=url,
                url_type=url_type,
                status='pending'
            )
            session.add(scrape_url)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error adding scrape URL: {e}")
            return False
        finally:
            session.close()
    
    def get_pending_urls(self, limit: int = 100) -> List[ScrapeURL]:
        """Get pending URLs to scrape"""
        session = self.get_session()
        try:
            urls = session.query(ScrapeURL).filter_by(status='pending').limit(limit).all()
            return urls
        finally:
            session.close()
    
    def update_url_status(self, url_id: int, status: str, error: Optional[str] = None):
        """Update URL processing status"""
        session = self.get_session()
        try:
            scrape_url = session.query(ScrapeURL).filter_by(id=url_id).first()
            if scrape_url:
                scrape_url.status = status
                scrape_url.attempts += 1
                if error:
                    scrape_url.last_error = error
                scrape_url.last_attempt_at = datetime.utcnow()
                if status == 'completed':
                    scrape_url.completed_at = datetime.utcnow()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating URL status: {e}")
        finally:
            session.close()
    
    def create_scrape_run(self) -> str:
        """Create a new scrape run record"""
        session = self.get_session()
        try:
            run = ScrapeRun()
            session.add(run)
            session.commit()
            return run.run_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating scrape run: {e}")
            return None
        finally:
            session.close()
    
    def update_scrape_run(self, run_id: str, stats: Dict):
        """Update scrape run statistics"""
        session = self.get_session()
        try:
            run = session.query(ScrapeRun).filter_by(run_id=run_id).first()
            if run:
                for key, value in stats.items():
                    if hasattr(run, key):
                        setattr(run, key, value)
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating scrape run: {e}")
        finally:
            session.close()
    
    def log_error(self, error_data: Dict):
        """Log a scrape error"""
        session = self.get_session()
        try:
            error = ScrapeError(
                url=error_data.get('url'),
                error_type=error_data.get('error_type'),
                error_message=error_data.get('error_message'),
                status_code=error_data.get('status_code'),
                attempt_count=error_data.get('attempt_count', 1),
                traceback=error_data.get('traceback'),
                run_id=error_data.get('run_id')
            )
            session.add(error)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error logging error: {e}")
        finally:
            session.close()
```

### 2.9 Main Scraper Pipeline

```python
# main.py
import asyncio
import click
from loguru import logger
from typing import List, Dict, Any
from datetime import datetime
import json
import time

from app.config import settings
from app.crawler.base import BaseCrawler
from app.crawler.discovery import URLDiscovery
from app.extractors.product import ProductExtractor
from app.pipelines.processor import DataProcessor
from app.storage.postgres import DatabaseRepository
from app.storage.export import JSONExporter
from app.utils.logging import setup_logging

# Setup logging
setup_logging()

class WafilifeScraper:
    def __init__(self):
        self.db = DatabaseRepository()
        self.discovery = URLDiscovery()
        self.extractor = ProductExtractor()
        self.processor = DataProcessor()
        self.exporter = JSONExporter()
        
        self.run_id = None
        self.stats = {
            'total_urls_discovered': 0,
            'total_products_processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'updated': 0,
            'new_products': 0,
            'duplicates': 0,
            'avg_response_time': 0,
        }
        self.start_time = None
        self.end_time = None
    
    async def run_discovery(self):
        """Discover product URLs"""
        logger.info("Starting URL discovery...")
        
        # Discover from sitemap
        sitemap_urls = await self.discovery.discover_from_sitemap()
        logger.info(f"Discovered {len(sitemap_urls)} URLs from sitemap")
        
        # Discover from categories
        category_urls = await self.discovery.discover_from_categories()
        logger.info(f"Discovered {len(category_urls)} URLs from categories")
        
        # Combine and deduplicate
        all_urls = list(set(sitemap_urls + category_urls))
        logger.info(f"Total unique URLs discovered: {len(all_urls)}")
        
        # Store in database
        added_count = 0
        for url in all_urls:
            if self.db.add_scrape_url(url, 'product'):
                added_count += 1
        
        self.stats['total_urls_discovered'] = added_count
        logger.info(f"Added {added_count} URLs to scrape queue")
        
        return all_urls
    
    async def run_scrape(self, limit: int = 0):
        """Run the scraping process"""
        self.start_time = time.time()
        self.run_id = self.db.create_scrape_run()
        
        if not self.run_id:
            logger.error("Failed to create scrape run")
            return
        
        logger.info(f"Starting scrape run {self.run_id}")
        
        # Get URLs to scrape
        pending_urls = self.db.get_pending_urls(limit if limit > 0 else 1000)
        total_urls = len(pending_urls)
        
        logger.info(f"Processing {total_urls} URLs")
        
        # Process URLs
        async with BaseCrawler() as crawler:
            for idx, url_record in enumerate(pending_urls):
                if settings.TEST_MODE and idx >= settings.MAX_PRODUCTS:
                    break
                
                try:
                    # Update status
                    self.db.update_url_status(url_record.id, 'processing')
                    
                    # Fetch page
                    page_data = await crawler.fetch(url_record.url)
                    
                    if not page_data:
                        self.db.update_url_status(url_record.id, 'failed', 'No data received')
                        self.stats['failed'] += 1
                        continue
                    
                    # Extract product data
                    product_data = self.extractor.extract(page_data)
                    
                    if not product_data:
                        self.db.update_url_status(url_record.id, 'failed', 'No product data extracted')
                        self.stats['failed'] += 1
                        continue
                    
                    # Process and normalize
                    processed_data = self.processor.process(product_data)
                    
                    # Compute content hash
                    content_hash = crawler.compute_hash(processed_data)
                    processed_data['content_hash'] = content_hash
                    processed_data['last_scraped_at'] = datetime.utcnow()
                    
                    # Save to database
                    product_id, operation = self.db.upsert_product(processed_data)
                    
                    if product_id:
                        self.db.update_url_status(url_record.id, 'completed')
                        self.stats['successful'] += 1
                        
                        if operation == 'new':
                            self.stats['new_products'] += 1
                        elif operation == 'updated':
                            self.stats['updated'] += 1
                        else:
                            self.stats['duplicates'] += 1
                    else:
                        self.db.update_url_status(url_record.id, 'failed', 'Database error')
                        self.stats['failed'] += 1
                    
                    self.stats['total_products_processed'] += 1
                    
                    # Log progress
                    if (idx + 1) % 100 == 0:
                        logger.info(f"Processed {idx + 1}/{total_urls} URLs")
                
                except Exception as e:
                    logger.error(f"Error processing {url_record.url}: {e}")
                    self.db.update_url_status(url_record.id, 'failed', str(e))
                    self.db.log_error({
                        'url': url_record.url,
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'run_id': self.run_id
                    })
                    self.stats['failed'] += 1
        
        self.end_time = time.time()
        self._finalize_run()
        
        # Export data
        await self.export_results()
        
        # Print summary
        self.print_summary()
    
    def _finalize_run(self):
        """Finalize the scrape run"""
        execution_time = self.end_time - self.start_time
        self.stats['total_execution_time'] = execution_time
        self.stats['avg_response_time'] = execution_time / max(self.stats['total_products_processed'], 1)
        
        self.db.update_scrape_run(self.run_id, self.stats)
        logger.info(f"Scrape run {self.run_id} completed")
    
    async def export_results(self):
        """Export results to JSON/JSONL"""
        logger.info("Exporting results...")
        
        # Get products from database
        products = self.db.get_products_for_export(limit=settings.SCRAPE_BATCH_SIZE)
        
        if products:
            self.exporter.export_products(products, format=settings.EXPORT_FORMAT)
            logger.info(f"Exported {len(products)} products to {settings.EXPORT_DIR}")
    
    def print_summary(self):
        """Print summary statistics"""
        logger.info("=" * 60)
        logger.info("SCRAPING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Run ID: {self.run_id}")
        logger.info(f"Total URLs Discovered: {self.stats['total_urls_discovered']}")
        logger.info(f"Total Products Processed: {self.stats['total_products_processed']}")
        logger.info(f"Successful: {self.stats['successful']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Skipped: {self.stats['skipped']}")
        logger.info(f"New Products: {self.stats['new_products']}")
        logger.info(f"Updated Products: {self.stats['updated']}")
        logger.info(f"Duplicates: {self.stats['duplicates']}")
        logger.info(f"Average Response Time: {self.stats['avg_response_time']:.2f}s")
        logger.info(f"Total Execution Time: {self.stats['total_execution_time']:.2f}s")
        logger.info("=" * 60)

@click.group()
def cli():
    """Wafilife.com Product Scraper"""
    pass

@cli.command()
def discover():
    """Discover product URLs"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.run_discovery())

@cli.command()
@click.option('--limit', default=0, help='Limit number of products to scrape')
def scrape(limit):
    """Scrape products"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.run_scrape(limit))

@cli.command()
@click.option('--format', default='jsonl', help='Export format (json, jsonl)')
def export(format):
    """Export scraped data"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.export_results())

@cli.command()
def stats():
    """Show scraping statistics"""
    scraper = WafilifeScraper()
    scraper.print_summary()

@cli.command()
def retry_failed():
    """Retry failed URLs"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.retry_failed())

if __name__ == '__main__':
    cli()
```

### 2.10 Laravel Import API

```php
<?php
// app/Http/Controllers/API/ProductImportController.php

namespace App\Http\Controllers\API;

use App\Http\Controllers\Controller;
use App\Http\Requests\ProductImportRequest;
use App\Models\Product;
use App\Models\Author;
use App\Models\Publisher;
use App\Models\Category;
use App\Models\ProductImage;
use App\Models\ProductMetadata;
use App\Jobs\ProcessProductImport;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Http\JsonResponse;

class ProductImportController extends Controller
{
    /**
     * Import products from scraper
     */
    public function import(ProductImportRequest $request): JsonResponse
    {
        $batchSize = 100;
        $products = $request->input('products', []);
        
        if (empty($products)) {
            return response()->json([
                'success' => false,
                'message' => 'No products to import'
            ], 400);
        }
        
        $total = count($products);
        
        // Process in batches
        for ($i = 0; $i < $total; $i += $batchSize) {
            $batch = array_slice($products, $i, $batchSize);
            ProcessProductImport::dispatch($batch);
        }
        
        return response()->json([
            'success' => true,
            'message' => "Queued {$total} products for import",
            'total' => $total
        ]);
    }
    
    /**
     * Process a batch of products (called by job)
     */
    public function processBatch(array $products): array
    {
        $stats = [
            'processed' => 0,
            'created' => 0,
            'updated' => 0,
            'failed' => 0
        ];
        
        DB::transaction(function () use ($products, &$stats) {
            foreach ($products as $productData) {
                try {
                    $this->upsertProduct($productData);
                    $stats['processed']++;
                    $stats['created']++;
                } catch (\Exception $e) {
                    Log::error('Product import failed', [
                        'product' => $productData['external_id'] ?? 'unknown',
                        'error' => $e->getMessage()
                    ]);
                    $stats['failed']++;
                }
            }
        });
        
        return $stats;
    }
    
    /**
     * Upsert a single product
     */
    private function upsertProduct(array $data): Product
    {
        // Find existing product
        $product = $this->findExistingProduct($data);
        
        if ($product) {
            // Update existing
            $this->updateProduct($product, $data);
        } else {
            // Create new
            $product = $this->createProduct($data);
        }
        
        return $product;
    }
    
    /**
     * Find existing product using various identifiers
     */
    private function findExistingProduct(array $data): ?Product
    {
        $product = null;
        
        // Try external ID first
        if (!empty($data['external_id'])) {
            $product = Product::where('external_id', $data['external_id'])->first();
        }
        
        // Try URL
        if (!$product && !empty($data['url'])) {
            $product = Product::where('url', $data['url'])->first();
        }
        
        // Try ISBN
        if (!$product && !empty($data['isbn'])) {
            $product = Product::where('isbn', $data['isbn'])->first();
        }
        
        // Try SKU
        if (!$product && !empty($data['sku'])) {
            $product = Product::where('sku', $data['sku'])->first();
        }
        
        return $product;
    }
    
    /**
     * Create a new product
     */
    private function createProduct(array $data): Product
    {
        $product = new Product();
        $this->fillProduct($product, $data);
        $product->save();
        
        // Handle relationships
        $this->syncAuthors($product, $data['authors'] ?? []);
        $this->syncCategories($product, $data['categories'] ?? []);
        $this->syncImages($product, $data['images'] ?? []);
        $this->syncMetadata($product, $data['metadata'] ?? []);
        
        // Handle publisher
        if (!empty($data['publisher'])) {
            $this->syncPublisher($product, $data['publisher']);
        }
        
        return $product;
    }
    
    /**
     * Update an existing product
     */
    private function updateProduct(Product $product, array $data): Product
    {
        $this->fillProduct($product, $data);
        $product->save();
        
        // Handle relationships (upsert)
        if (isset($data['authors'])) {
            $this->syncAuthors($product, $data['authors']);
        }
        
        if (isset($data['categories'])) {
            $this->syncCategories($product, $data['categories']);
        }
        
        if (isset($data['images'])) {
            $this->syncImages($product, $data['images']);
        }
        
        if (isset($data['metadata'])) {
            $this->syncMetadata($product, $data['metadata']);
        }
        
        if (isset($data['publisher'])) {
            $this->syncPublisher($product, $data['publisher']);
        }
        
        return $product;
    }
    
    /**
     * Fill product attributes
     */
    private function fillProduct(Product $product, array $data): void
    {
        $fillable = [
            'external_id', 'name', 'slug', 'url', 'description',
            'short_description', 'sku', 'isbn', 'regular_price',
            'selling_price', 'discount', 'stock_status', 'pages',
            'cover_type', 'edition', 'published_year', 'language',
            'source', 'source_url', 'content_hash'
        ];
        
        foreach ($fillable as $field) {
            if (array_key_exists($field, $data)) {
                $product->{$field} = $data[$field];
            }
        }
    }
    
    /**
     * Sync authors (many-to-many)
     */
    private function syncAuthors(Product $product, array $authors): void
    {
        $authorIds = [];
        
        foreach ($authors as $authorData) {
            $author = Author::updateOrCreate(
                ['name' => $authorData['name']],
                [
                    'external_id' => $authorData['external_id'] ?? null,
                    'slug' => $authorData['slug'] ?? $this->createSlug($authorData['name']),
                    'url' => $authorData['url'] ?? null
                ]
            );
            $authorIds[] = $author->id;
        }
        
        $product->authors()->sync($authorIds);
    }
    
    /**
     * Sync categories (many-to-many)
     */
    private function syncCategories(Product $product, array $categories): void
    {
        $categoryIds = [];
        
        foreach ($categories as $categoryData) {
            $category = Category::updateOrCreate(
                ['name' => $categoryData['name']],
                [
                    'external_id' => $categoryData['external_id'] ?? null,
                    'slug' => $categoryData['slug'] ?? $this->createSlug($categoryData['name']),
                    'url' => $categoryData['url'] ?? null,
                    'parent_id' => $this->resolveParentCategory($categoryData)
                ]
            );
            $categoryIds[] = $category->id;
        }
        
        $product->categories()->sync($categoryIds);
    }
    
    /**
     * Sync images
     */
    private function syncImages(Product $product, array $images): void
    {
        $product->images()->delete();
        
        foreach ($images as $index => $imageData) {
            $product->images()->create([
                'url' => $imageData['url'],
                'thumbnail_url' => $imageData['thumbnail_url'] ?? null,
                'is_main' => $imageData['is_main'] ?? ($index === 0),
                'sort_order' => $imageData['sort_order'] ?? $index
            ]);
        }
    }
    
    /**
     * Sync metadata
     */
    private function syncMetadata(Product $product, array $metadata): void
    {
        $product->metadata()->delete();
        
        foreach ($metadata as $metaData) {
            $product->metadata()->create([
                'key' => $metaData['key'],
                'value' => $metaData['value']
            ]);
        }
    }
    
    /**
     * Sync publisher
     */
    private function syncPublisher(Product $product, array $publisherData): void
    {
        if (!empty($publisherData['name'])) {
            $publisher = Publisher::updateOrCreate(
                ['name' => $publisherData['name']],
                [
                    'external_id' => $publisherData['external_id'] ?? null,
                    'slug' => $publisherData['slug'] ?? $this->createSlug($publisherData['name']),
                    'url' => $publisherData['url'] ?? null
                ]
            );
            $product->publisher_id = $publisher->id;
            $product->save();
        }
    }
    
    /**
     * Create URL-friendly slug
     */
    private function createSlug(string $name): string
    {
        $slug = strtolower($name);
        $slug = preg_replace('/\s+/', '-', $slug);
        $slug = preg_replace('/[^a-z0-9\-]/', '', $slug);
        return trim($slug, '-');
    }
    
    /**
     * Resolve parent category
     */
    private function resolveParentCategory(array $categoryData): ?int
    {
        if (!empty($categoryData['parent']) && is_array($categoryData['parent'])) {
            $parent = Category::firstOrCreate(
                ['name' => $categoryData['parent']['name']],
                [
                    'slug' => $this->createSlug($categoryData['parent']['name']),
                    'url' => $categoryData['parent']['url'] ?? null
                ]
            );
            return $parent->id;
        }
        return null;
    }
}
```

### 2.11 Laravel Request Validation

```php
<?php
// app/Http/Requests/ProductImportRequest.php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class ProductImportRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // Add API key validation here
    }
    
    public function rules(): array
    {
        return [
            'products' => 'required|array|max:500',
            'products.*.external_id' => 'nullable|string|max:255',
            'products.*.name' => 'required|string|max:500',
            'products.*.slug' => 'nullable|string|max:255',
            'products.*.url' => 'required|url|max:1000',
            'products.*.description' => 'nullable|string',
            'products.*.short_description' => 'nullable|string',
            'products.*.sku' => 'nullable|string|max:100',
            'products.*.isbn' => 'nullable|string|max:50',
            'products.*.regular_price' => 'nullable|numeric|min:0',
            'products.*.selling_price' => 'nullable|numeric|min:0',
            'products.*.discount' => 'nullable|numeric|min:0|max:100',
            'products.*.stock_status' => 'nullable|string|in:in_stock,out_of_stock,on_backorder',
            'products.*.pages' => 'nullable|integer|min:0',
            'products.*.cover_type' => 'nullable|string|max:100',
            'products.*.edition' => 'nullable|string|max:100',
            'products.*.published_year' => 'nullable|integer|min:1000|max:' . date('Y'),
            'products.*.language' => 'nullable|string|max:50',
            'products.*.authors' => 'nullable|array',
            'products.*.authors.*.name' => 'required|string|max:255',
            'products.*.authors.*.url' => 'nullable|url|max:1000',
            'products.*.authors.*.external_id' => 'nullable|string|max:255',
            'products.*.publisher' => 'nullable|array',
            'products.*.publisher.name' => 'required_with:publisher|string|max:255',
            'products.*.publisher.url' => 'nullable|url|max:1000',
            'products.*.categories' => 'nullable|array',
            'products.*.categories.*.name' => 'required|string|max:255',
            'products.*.categories.*.url' => 'nullable|url|max:1000',
            'products.*.images' => 'nullable|array',
            'products.*.images.*.url' => 'required|url|max:1000',
            'products.*.images.*.is_main' => 'nullable|boolean',
            'products.*.images.*.sort_order' => 'nullable|integer|min:0',
            'products.*.metadata' => 'nullable|array',
            'products.*.metadata.*.key' => 'required|string|max:255',
            'products.*.metadata.*.value' => 'nullable',
            'products.*.content_hash' => 'nullable|string|max:64',
        ];
    }
}
```

### 2.12 Docker Setup

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p logs exports

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Run scraper
CMD ["python", "main.py"]
```

### 2.13 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: wafilife
      POSTGRES_USER: wafilife
      POSTGRES_PASSWORD: wafilife
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U wafilife"]
      interval: 10s
      timeout: 5s
      retries: 5

  scraper:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: wafilife
      DB_USER: wafilife
      DB_PASSWORD: wafilife
    volumes:
      - ./logs:/app/logs
      - ./exports:/app/exports
    command: python main.py scrape --limit 100

volumes:
  postgres_data:
```

## 3. Production Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Production Environment                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐      ┌─────────────┐    ┌─────────────┐ │
│  │  PostgreSQL  │      │  Laravel    │    │  Redis      │ │
│  │  (Primary)   │◄────►│  Application│    │  (Queue)    │ │
│  └─────────────┘      └─────────────┘    └─────────────┘ │
│         ▲                    ▲                   ▲          │
│         │                    │                   │          │
│  ┌─────────────┐      ┌─────────────┐    ┌─────────────┐ │
│  │  Scraper    │      │  API Gateway│    │  Horizon    │ │
│  │  (Worker)   │──────►│  (Nginx)    │    │  (Queue     │ │
│  └─────────────┘      └─────────────┘    │   Worker)   │ │
│                                            └─────────────┘ │
│         │                                                   │
│  ┌─────────────┐                                           │
│  │  Monitoring  │                                           │
│  │  (Prometheus)│                                           │
│  └─────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

## 4. Example JSON Output

```json
{
  "external_id": "978-984-93839-7-1",
  "name": "বাংলা সাহিত্যের ইতিহাস",
  "slug": "bangla-sahityer-itihas",