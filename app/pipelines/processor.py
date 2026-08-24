"""Data processor pipeline - normalizes extracted product dicts before storage."""
import re
from typing import Optional, Dict, Any

from app.models.pydantic_models import Product
from app.utils.normalizers import (
    normalize_isbn,
    normalize_price,
    create_slug,
)


class DataProcessor:
    """Post-extraction processing: cleaning, derived fields, validation"""

    def process(self, product: Product) -> Dict[str, Any]:
        """Process a validated product model into a clean dict for upsert."""
        data = product.model_dump()

        data['name'] = self._clean_name(data.get('name'))

        # Slug fallback
        if not data.get('slug'):
            data['slug'] = create_slug(data.get('name') or '') or None
        if not data['slug'] and data.get('url'):
            data['slug'] = data['url'].rstrip('/').split('/')[-1]

        # Derived discount when missing (percentage off regular price)
        if data.get('discount') is None:
            data['discount'] = self._compute_discount(
                data.get('regular_price'), data.get('selling_price')
            )

        # Sanity: selling price must not exceed regular price
        if data.get('regular_price') and data.get('selling_price'):
            if data['selling_price'] > data['regular_price']:
                data['regular_price'], data['selling_price'] = \
                    data['selling_price'], data['regular_price']

        # Normalize ISBN
        data['isbn'] = normalize_isbn(data.get('isbn'))
        if not data.get('isbn') and data.get('sku'):
            candidate = re.sub(r'[^\dX]', '', str(data['sku']).upper())
            if len(candidate) in (10, 13):
                data['isbn'] = candidate

        # Source metadata
        data.setdefault('source', 'wafilife')
        data.setdefault('source_url', data.get('url'))

        return data

    @staticmethod
    def _clean_name(name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        return re.sub(r'\s+', ' ', name).strip()[:500]

    @staticmethod
    def _compute_discount(regular: Optional[float], selling: Optional[float]) -> Optional[float]:
        """Compute percentage discount between regular and selling prices"""
        if not regular or selling is None or regular <= 0:
            return None
        if selling >= regular:
            return 0.0
        return round((regular - selling) / regular * 100, 2)
