"""REST API for scraped wafilife data.

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000

Endpoints:
    GET /api/products          - paginated list (filters: q, category, author, publisher,
                                 in_stock, min_price, max_price, sort)
    GET /api/products/{slug}   - single product by slug or external_id
    GET /api/categories        - all categories
    GET /api/authors           - all authors
    GET /api/publishers        - all publishers
    GET /api/stats             - scrape statistics
    /images/...                - downloaded images (static)
"""
from typing import List, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.database import (
    Author, Category, Product, ProductImage, ProductMetadata,
    Publisher, ScrapeError, ScrapeRun, ScrapeURL,
)
from app.storage.postgres import DatabaseRepository
from app.utils.logging import setup_logging

setup_logging()

app = FastAPI(
    title="Wafilife Scraper API",
    description="REST API for scraped book data from wafilife.com",
    version="1.0.0",
)

# Serve downloaded images if present
import os
if os.path.isdir(os.path.join("exports", "images")):
    app.mount("/images", StaticFiles(directory="exports/images"), name="images")


# ---- Response schemas ----

class AuthorOut(BaseModel):
    name: str
    url: Optional[str] = None


class PublisherOut(BaseModel):
    name: str
    url: Optional[str] = None


class CategoryOut(BaseModel):
    name: str
    url: Optional[str] = None


class ImageOut(BaseModel):
    url: str
    is_main: bool = False
    sort_order: int = 0


class MetadataOut(BaseModel):
    key: str
    value: Optional[str] = None


class ProductOut(BaseModel):
    external_id: str
    name: str
    slug: str
    url: str
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
    authors: List[AuthorOut] = []
    publisher: Optional[PublisherOut] = None
    categories: List[CategoryOut] = []
    images: List[ImageOut] = []
    metadata: List[MetadataOut] = []
    last_scraped_at: Optional[str] = None


class ProductListOut(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[ProductOut]


class SimpleRef(BaseModel):
    id: int
    name: str
    slug: str
    url: Optional[str] = None


class RefListOut(BaseModel):
    total: int
    items: List[SimpleRef]


def _product_to_out(p: Product) -> ProductOut:
    return ProductOut(
        external_id=p.external_id,
        name=p.name,
        slug=p.slug,
        url=p.url,
        description=p.description,
        short_description=p.short_description,
        sku=p.sku,
        isbn=p.isbn,
        regular_price=p.regular_price,
        selling_price=p.selling_price,
        discount=p.discount,
        stock_status=p.stock_status,
        pages=p.pages,
        cover_type=p.cover_type,
        edition=p.edition,
        published_year=p.published_year,
        language=p.language,
        authors=[AuthorOut(name=a.name, url=a.url) for a in p.authors],
        publisher=PublisherOut(name=p.publisher.name, url=p.publisher.url) if p.publisher else None,
        categories=[CategoryOut(name=c.name, url=c.url) for c in p.categories],
        images=[
            ImageOut(url=i.url, is_main=i.is_main, sort_order=i.sort_order)
            for i in sorted(p.images, key=lambda x: x.sort_order)
        ],
        metadata=[MetadataOut(key=m.key, value=m.value) for m in p.meta],
        last_scraped_at=p.last_scraped_at.isoformat() if p.last_scraped_at else None,
    )


def get_db():
    repo = DatabaseRepository()
    session = repo.get_session()
    try:
        yield session
    finally:
        session.close()


PRODUCT_LOAD = (
    selectinload(Product.authors),
    selectinload(Product.publisher),
    selectinload(Product.categories),
    selectinload(Product.images),
    selectinload(Product.meta),
)


@app.get("/")
def root():
    return {
        "service": "wafilife-scraper-api",
        "docs": "/docs",
        "endpoints": [
            "/api/products", "/api/products/{slug}",
            "/api/categories", "/api/authors", "/api/publishers", "/api/stats",
        ],
    }


@app.get("/api/products", response_model=ProductListOut)
def list_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="Search name/description"),
    category: Optional[str] = Query(None, description="Filter by category name"),
    author: Optional[str] = Query(None, description="Filter by author name"),
    publisher: Optional[str] = Query(None, description="Filter by publisher name"),
    in_stock: Optional[bool] = Query(None, description="Filter by stock status"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    sort: str = Query("id_desc", pattern="^(id_asc|id_desc|price_asc|price_desc|name_asc|name_desc|newest)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Product).options(*PRODUCT_LOAD)

    # Filters
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Product.name.ilike(like),
            Product.description.ilike(like),
            Product.isbn.ilike(like),
        ))
    if category:
        query = query.join(Product.categories).filter(Category.name == category)
    if author:
        query = query.join(Product.authors).filter(Author.name == author)
    if publisher:
        query = query.join(Product.publisher).filter(Publisher.name == publisher)
    if in_stock is not None:
        query = query.filter(Product.stock_status == ('in_stock' if in_stock else 'out_of_stock'))
    if min_price is not None:
        query = query.filter(Product.selling_price >= min_price)
    if max_price is not None:
        query = query.filter(Product.selling_price <= max_price)

    total = query.count()

    order_by = {
        'id_asc': Product.id.asc(),
        'id_desc': Product.id.desc(),
        'price_asc': Product.selling_price.asc().nulls_last(),
        'price_desc': Product.selling_price.desc().nulls_last(),
        'name_asc': Product.name.asc(),
        'name_desc': Product.name.desc(),
        'newest': Product.last_scraped_at.desc().nulls_last(),
    }[sort]

    products = (
        query.order_by(order_by)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return ProductListOut(
        total=total,
        page=page,
        per_page=per_page,
        items=[_product_to_out(p) for p in products],
    )


@app.get("/api/products/{identifier}", response_model=ProductOut)
def get_product(identifier: str, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(*PRODUCT_LOAD)
        .filter(or_(
            Product.slug == identifier,
            Product.external_id == identifier,
        ))
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_out(product)


@app.get("/api/categories", response_model=RefListOut)
def list_categories(db: Session = Depends(get_db)):
    rows = db.query(Category).order_by(Category.name).all()
    return RefListOut(
        total=len(rows),
        items=[SimpleRef(id=r.id, name=r.name, slug=r.slug, url=r.url) for r in rows],
    )


@app.get("/api/authors", response_model=RefListOut)
def list_authors(db: Session = Depends(get_db)):
    rows = db.query(Author).order_by(Author.name).all()
    return RefListOut(
        total=len(rows),
        items=[SimpleRef(id=r.id, name=r.name, slug=r.slug, url=r.url) for r in rows],
    )


@app.get("/api/publishers", response_model=RefListOut)
def list_publishers(db: Session = Depends(get_db)):
    rows = db.query(Publisher).order_by(Publisher.name).all()
    return RefListOut(
        total=len(rows),
        items=[SimpleRef(id=r.id, name=r.name, slug=r.slug, url=r.url) for r in rows],
    )


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    last_run = db.query(ScrapeRun).order_by(ScrapeRun.id.desc()).first()
    counts = {
        'products': db.query(func.count(Product.id)).scalar(),
        'authors': db.query(func.count(Author.id)).scalar(),
        'publishers': db.query(func.count(Publisher.id)).scalar(),
        'categories': db.query(func.count(Category.id)).scalar(),
        'urls_pending': db.query(func.count(ScrapeURL.id)).filter_by(status='pending').scalar(),
        'urls_completed': db.query(func.count(ScrapeURL.id)).filter_by(status='completed').scalar(),
        'urls_failed': db.query(func.count(ScrapeURL.id)).filter_by(status='failed').scalar(),
        'errors': db.query(func.count(ScrapeError.id)).scalar(),
    }
    return {
        'counts': counts,
        'last_run': {
            'run_id': last_run.run_id,
            'started_at': last_run.started_at.isoformat() if last_run.started_at else None,
            'completed_at': last_run.completed_at.isoformat() if last_run.completed_at else None,
            'status': last_run.status,
            'successful': last_run.successful,
            'failed': last_run.failed,
            'new_products': last_run.new_products,
            'updated': last_run.updated,
            'total_execution_time': last_run.total_execution_time,
        } if last_run else None,
    }


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)
