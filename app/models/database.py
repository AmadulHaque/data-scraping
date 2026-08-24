from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text,
    DateTime, Boolean, ForeignKey, UniqueConstraint,
    Index, BigInteger, Table
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
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
    # NB: 'metadata' is reserved by SQLAlchemy declarative; use 'meta'
    meta = relationship('ProductMetadata', back_populates='product', cascade='all, delete-orphan')

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
    product = relationship('Product', back_populates='meta')

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
