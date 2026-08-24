from typing import List, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger

from app.utils.normalizers import normalize_text

HOME_MARKERS = ('home', 'হোম', 'প্রচ্ছদ')


class CategoryExtractor:
    """Extract category hierarchy from breadcrumbs and category pages"""

    def extract_breadcrumb(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract ordered category chain from WooCommerce breadcrumb"""
        categories = []

        breadcrumb = soup.find('nav', class_='woocommerce-breadcrumb')
        if not breadcrumb:
            return categories

        for link in breadcrumb.find_all('a'):
            text = normalize_text(link.text)
            href = link.get('href')
            if text and text.lower() not in HOME_MARKERS and '/product-category/' in (href or ''):
                categories.append({'name': text, 'url': href})

        # Current (last, unlinked) category
        current = breadcrumb.find_all(text=True)
        return categories

    def extract_from_json_ld(self, json_ld: List[Dict]) -> List[Dict[str, Any]]:
        """Extract category chain from BreadcrumbList JSON-LD"""
        categories = []
        for data in json_ld:
            if not isinstance(data, dict):
                continue
            if data.get('@type') == 'BreadcrumbList':
                for item in data.get('itemListElement', []):
                    entry = item.get('item') if isinstance(item.get('item'), dict) else item
                    name = normalize_text(entry.get('name'))
                    link = entry.get('@id') or entry.get('url')
                    if name and link and '/product-category/' in link:
                        categories.append({'name': name, 'url': link})
                break
        return categories

    def extract_category_page_info(self, page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract name/description of a category listing page"""
        result: Dict[str, Any] = {'url': page_data.get('url')}
        soup = page_data.get('soup')

        try:
            if not soup:
                return result

            header = soup.find('header', class_='woocommerce-products-header')
            title_elem = header.find('h1') if header else soup.find('h1', class_='page-title')
            desc_elem = header.find(
                'div', class_='term-description'
            ) if header else soup.find('div', class_='term-description')

            if title_elem:
                result['name'] = normalize_text(title_elem.text)
            if desc_elem:
                result['description'] = normalize_text(desc_elem.text)
        except Exception as e:
            logger.error(f"Error extracting category page: {e}")

        return result
