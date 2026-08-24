from pydantic_settings import BaseSettings
from pydantic import validator


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
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Site Settings
    BASE_URL: str = "https://www.wafilife.com"
    SITEMAP_URL: str = "https://www.wafilife.com/sitemap.xml"
    PRODUCT_URL_PATTERN: str = "/pd/"

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

    @validator("BASE_URL")
    def validate_base_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("BASE_URL must start with http:// or https://")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
