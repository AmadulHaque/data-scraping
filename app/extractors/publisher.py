from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger

from app.utils.normalizers import normalize_text


class PublisherExtractor:
    """Extract publisher info from product/publisher pages"""

    def extract_from_product(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Extract publisher from product page meta or brand"""
        try:
            # Product meta link
            elem = soup.select_one(
                '.product_meta a[href*="publisher"], '
                '.publisher-name, .publisher-link'
            )
            if elem and normalize_text(elem.text):
                return {
                    'name': normalize_text(elem.text),
                    'url': elem.get('href'),
                }

            # JSON-LD brand fallback handled by product extractor; HTML fallback:
            brand_elem = soup.select_one('a[href*="brand"], .brand-name')
            if brand_elem and normalize_text(brand_elem.text):
                return {
                    'name': normalize_text(brand_elem.text),
                    'url': brand_elem.get('href'),
                }
        except Exception as e:
            logger.error(f"Error extracting publisher: {e}")
        return None

    def extract_from_publisher_page(self, page_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract publisher details from a publisher archive page"""
        try:
            soup = page_data.get('soup')
            if not soup:
                return None

            name_elem = soup.find('h1', class_='page-title') or soup.find('h1')
            desc_elem = soup.find('div', class_='term-description') or \
                        soup.find('div', class_='publisher-description')

            return {
                'name': normalize_text(name_elem.text) if name_elem else None,
                'description': normalize_text(desc_elem.text) if desc_elem else None,
                'url': page_data.get('url'),
            }
        except Exception as e:
            logger.error(f"Error extracting publisher page: {e}")
            return None
