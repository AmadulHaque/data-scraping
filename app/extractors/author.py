from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger
from urllib.parse import urljoin

from app.utils.normalizers import normalize_text


class AuthorExtractor:
    """Extract author info from product/author pages"""

    def extract_from_product(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract all authors mentioned on a product page"""
        authors = []
        seen = set()

        candidates = soup.select(
            '.product_meta a[href*="author"], '
            '.author-name, .author-link, '
            'span:contains("লেখক") + a'
        )
        for elem in candidates:
            name = normalize_text(elem.text)
            if name and name.lower() not in seen:
                seen.add(name.lower())
                authors.append({
                    'name': name,
                    'url': urljoin(elem.base if hasattr(elem, 'base') else '', elem.get('href') or ''),
                })
        return authors

    def extract_from_author_page(self, page_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract author bio/details from an author archive page"""
        try:
            soup = page_data.get('soup')
            if not soup:
                return None

            name_elem = soup.find('h1', class_='page-title') or soup.find('h1')
            bio_elem = soup.find('div', class_='author-bio') or \
                       soup.find('div', class_='term-description')

            return {
                'name': normalize_text(name_elem.text) if name_elem else None,
                'bio': normalize_text(bio_elem.text) if bio_elem else None,
                'url': page_data.get('url'),
            }
        except Exception as e:
            logger.error(f"Error extracting author page: {e}")
            return None
