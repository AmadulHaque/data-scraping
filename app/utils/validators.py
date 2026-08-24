import re
from typing import Optional, Any, Dict
from urllib.parse import urlparse


def is_valid_url(url: Optional[str]) -> bool:
    """Validate URL format"""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return all([parsed.scheme in ('http', 'https'), parsed.netloc])
    except Exception:
        return False


def is_valid_isbn(isbn: str) -> bool:
    """Check if string looks like ISBN-10 or ISBN-13"""
    if not isbn:
        return False
    cleaned = re.sub(r'[-\s]', '', isbn)
    return bool(re.match(r'^\d{9}[\dXx]$|^\d{13}$', cleaned))


def validate_product_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize product data before storage.
    Raises ValueError on invalid required fields."""
    if not data.get('url'):
        raise ValueError("Product URL is required")

    if not is_valid_url(data['url']):
        raise ValueError(f"Invalid product URL: {data['url']}")

    for field in ('regular_price', 'selling_price', 'discount'):
        value = data.get(field)
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            raise ValueError(f"Invalid {field}: {value}")

    year = data.get('published_year')
    if year is not None and not (1000 <= year <= 2100):
        raise ValueError(f"Invalid published_year: {year}")

    pages = data.get('pages')
    if pages is not None and (pages < 0 or pages > 100000):
        raise ValueError(f"Invalid pages: {pages}")

    return data
