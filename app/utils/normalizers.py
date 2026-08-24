import re
from typing import Optional, Any
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


_BN_DIGITS = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')


def _to_ascii_digits(text: str) -> str:
    """Convert Bengali numerals to ASCII digits"""
    return text.translate(_BN_DIGITS)


def normalize_price(price: Optional[Any]) -> Optional[float]:
    """Normalize price from various formats (handles Bengali numerals)"""
    if price is None:
        return None

    if isinstance(price, (int, float)):
        return float(price)

    if isinstance(price, str):
        cleaned = _to_ascii_digits(price)
        cleaned = re.sub(r'[^\d.,]', '', cleaned)
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

    cleaned = re.sub(r'[-/\s]', '', _to_ascii_digits(isbn))

    if re.match(r'^\d{10}(\d{3})?$', cleaned):
        return cleaned

    return isbn


def extract_year(text: Optional[str]) -> Optional[int]:
    """Extract year from text (handles Bengali numerals)"""
    if not text:
        return None

    match = re.search(r'\b(19|20)\d{2}\b', _to_ascii_digits(str(text)))
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None

    return None


def create_slug(name: str) -> str:
    """Create URL-friendly slug from name.
    Falls back to unicode-preserving slug for non-Latin names (e.g. Bengali)."""
    if not name:
        return ''

    slug = name.lower().strip()
    slug = re.sub(r'\s+', '-', slug)
    ascii_slug = re.sub(r'[^a-z0-9\-]', '', slug)
    ascii_slug = re.sub(r'-+', '-', ascii_slug).strip('-')
    if ascii_slug:
        return ascii_slug

    # Non-Latin name: keep unicode characters, strip only unsafe punctuation
    slug = re.sub(r'[^\w\u0980-\u09FF-]', '', slug, flags=re.UNICODE)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')
