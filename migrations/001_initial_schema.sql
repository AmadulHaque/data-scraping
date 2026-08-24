-- 001_initial_schema.sql
-- Core domain schema: products, authors, publishers, categories + relations

CREATE TABLE IF NOT EXISTS publishers (
    id BIGSERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE,
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(255) NOT NULL UNIQUE,
    url VARCHAR(1000),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS authors (
    id BIGSERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE,
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(255) NOT NULL UNIQUE,
    url VARCHAR(1000),
    bio TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE,
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(255) NOT NULL UNIQUE,
    url VARCHAR(1000),
    parent_id BIGINT REFERENCES categories(id),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    external_id VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(500) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    url VARCHAR(1000) NOT NULL UNIQUE,

    description TEXT,
    short_description TEXT,

    sku VARCHAR(100),
    isbn VARCHAR(50),

    regular_price DOUBLE PRECISION,
    selling_price DOUBLE PRECISION,
    discount DOUBLE PRECISION,
    stock_status VARCHAR(50),

    pages INTEGER,
    cover_type VARCHAR(100),
    edition VARCHAR(100),
    published_year INTEGER,
    language VARCHAR(50),

    publisher_id BIGINT REFERENCES publishers(id),

    source VARCHAR(50) DEFAULT 'wafilife',
    source_url VARCHAR(1000),
    content_hash VARCHAR(64),

    last_scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_images (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    url VARCHAR(1000) NOT NULL,
    thumbnail_url VARCHAR(1000),
    is_main BOOLEAN DEFAULT FALSE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_metadata (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    key VARCHAR(255) NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_product_metadata_key UNIQUE (product_id, key)
);

-- Association tables
CREATE TABLE IF NOT EXISTS product_authors (
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (product_id, author_id)
);

CREATE TABLE IF NOT EXISTS product_categories (
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (product_id, category_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_product_external_id ON products(external_id);
CREATE INDEX IF NOT EXISTS idx_product_slug ON products(slug);
CREATE INDEX IF NOT EXISTS idx_product_url ON products(url);
CREATE INDEX IF NOT EXISTS idx_product_isbn ON products(isbn);
CREATE INDEX IF NOT EXISTS idx_product_publisher ON products(publisher_id);
