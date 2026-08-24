from pydantic import BaseModel, Field, validator
from typing import Optional, List, Any
from datetime import datetime


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
    external_id: Optional[str] = None
    name: Optional[str] = None
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
