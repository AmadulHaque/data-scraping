-- 002_scrape_tables.sql
-- Scraper operational tables: URL queue, runs, errors

CREATE TABLE IF NOT EXISTS scrape_urls (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(1000) NOT NULL UNIQUE,
    url_type VARCHAR(50),                -- product, category, author, publisher
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, completed, failed
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,
    status_code INTEGER,
    last_attempt_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL UNIQUE,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',

    total_urls_discovered INTEGER DEFAULT 0,
    total_products_processed INTEGER DEFAULT 0,
    successful INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    updated INTEGER DEFAULT 0,
    new_products INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,

    avg_response_time DOUBLE PRECISION,
    total_execution_time DOUBLE PRECISION,

    config JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrape_errors (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(1000) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT,
    status_code INTEGER,
    attempt_count INTEGER DEFAULT 1,
    traceback TEXT,
    run_id VARCHAR(36) REFERENCES scrape_runs(run_id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_scrape_urls_status ON scrape_urls(status);
CREATE INDEX IF NOT EXISTS idx_scrape_urls_url_type ON scrape_urls(url_type);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_status ON scrape_runs(status);
CREATE INDEX IF NOT EXISTS idx_scrape_errors_run ON scrape_errors(run_id);
