from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger
import re
from urllib.parse import urlparse

from app.models.pydantic_models import (
    Product, Author, Publisher, Category, ProductImage, ProductMetadata
)
from app.utils.normalizers import normalize_text, normalize_price, _to_ascii_digits

# Anchor href prefixes used by wafilife's custom theme
AUTHOR_HREF = '/cat/books/author/'
PUBLISHER_HREF = '/cat/books/publisher/'
SUBJECT_HREF = '/cat/books/subject/'


class ProductExtractor:
    """Extract product data from HTML and JSON-LD"""

    @staticmethod
    def _slug_from_url(url: str) -> str:
        """Extract slug: for wafilife URLs like /name/pd/4 -> 'name'"""
        path = urlparse(url).path.rstrip('/')
        parts = path.split('/')
        if 'pd' in parts:
            idx = parts.index('pd')
            if idx > 0:
                return parts[idx - 1]
        return parts[-1]

    def extract(self, page_data: Dict[str, Any]) -> Optional[Product]:
        """Extract product data from page data"""
        try:
            soup = page_data.get('soup')
            json_ld = page_data.get('json_ld', [])
            url = page_data.get('url')

            if not soup:
                return None

            # Try JSON-LD first
            product_data = self._extract_from_json_ld(json_ld, url)

            # Fallback to HTML extraction
            if not product_data:
                product_data = self._extract_from_html(soup, url)

            if not product_data or not product_data.get('name'):
                return None

            # Ensure required fields exist
            if not product_data.get('external_id'):
                product_data['external_id'] = product_data.get('sku') or product_data.get('slug') or url

            # Merge HTML-only attributes (ISBN, pages etc.) missing in JSON-LD
            html_extra = self._extract_attributes(soup)
            for key, value in html_extra.items():
                if value is not None and not product_data.get(key):
                    product_data[key] = value

            # Merge HTML link-based data (authors/publisher/categories)
            html_links = self._extract_cat_links(soup)
            if not product_data.get('categories') and html_links['subjects']:
                product_data['categories'] = html_links['subjects']
            if not product_data.get('authors') and html_links['authors']:
                product_data['authors'] = html_links['authors']
            if not product_data.get('publisher') and html_links['publishers']:
                product_data['publisher'] = html_links['publishers'][0]

            # Merge HTML images when JSON-LD had none
            if not product_data.get('images'):
                product_data['images'] = self._extract_images(soup)

            # Validate through pydantic model
            product = Product(**product_data)
            return product

        except Exception as e:
            logger.error(f"Error extracting product from {page_data.get('url')}: {e}")
            return None

    def _extract_from_json_ld(self, json_ld: List[Dict], url: str) -> Optional[Dict]:
        """Extract product data from JSON-LD"""
        product_data = {}

        for data in self._iter_json_ld(json_ld):
            if data.get('@type') == 'Product' or 'Product' in (data.get('@type') or []):
                offers = data.get('offers', {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}

                price_spec = offers.get('priceSpecification', {})
                if isinstance(price_spec, list):
                    price_spec = price_spec[0] if price_spec else {}

                selling_price = normalize_price(offers.get('price'))
                regular_price = normalize_price(price_spec.get('price')) if price_spec else selling_price

                product_data.update({
                    'external_id': str(data.get('sku') or data.get('productID') or ''),
                    'name': normalize_text(data.get('name')),
                    'url': url,
                    'slug': self._slug_from_url(url),
                    'description': normalize_text(data.get('description')),
                    'regular_price': regular_price,
                    'selling_price': selling_price,
                    'stock_status': 'in_stock' if 'InStock' in (offers.get('availability') or '') else 'out_of_stock',
                    'sku': data.get('sku'),
                    'isbn': data.get('isbn'),
                })

                # Images
                images = []
                image_field = data.get('image')
                if isinstance(image_field, list):
                    items = image_field
                elif isinstance(image_field, dict):
                    items = [image_field]
                elif isinstance(image_field, str):
                    items = [image_field]
                else:
                    items = []

                for idx, img in enumerate(items):
                    img_url = img if isinstance(img, str) else (img.get('url') or img.get('@id'))
                    if img_url:
                        images.append({'url': img_url, 'is_main': idx == 0, 'sort_order': idx})
                product_data['images'] = images

                # Brand/Publisher (prefer explicit publisher, fall back to brand)
                publisher = data.get('publisher') or {}
                if isinstance(publisher, list):
                    publisher = publisher[0] if publisher else {}
                if not publisher:
                    publisher = data.get('brand') or {}
                    if isinstance(publisher, list):
                        publisher = publisher[0] if publisher else {}
                if isinstance(publisher, str):
                    publisher = {'name': publisher}
                if publisher and publisher.get('name'):
                    product_data['publisher'] = {
                        'name': normalize_text(publisher.get('name')),
                        'url': publisher.get('@id') or publisher.get('url')
                    }

                # Categories from breadcrumbs
                product_data['categories'] = self._extract_categories_from_json_ld(json_ld)

                return product_data

        return None

    def _extract_from_html(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Extract product data from HTML"""
        try:
            slug = self._slug_from_url(url)
            product_data = {
                'url': url,
                'slug': slug,
            }

            # Product name
            name_elem = soup.find('h1', class_='product_title') or soup.find('h1')
            if name_elem:
                product_data['name'] = normalize_text(name_elem.text)

            # Price
            price_elem = soup.find('p', class_='price') or soup.find('span', class_='price')
            if price_elem:
                regular_elem = price_elem.find('del')
                sale_elem = price_elem.find('ins')

                if regular_elem and sale_elem:
                    product_data['regular_price'] = normalize_price(regular_elem.text)
                    product_data['selling_price'] = normalize_price(sale_elem.text)
                else:
                    price_val = normalize_price(price_elem.text)
                    product_data['regular_price'] = price_val
                    product_data['selling_price'] = price_val

            # Description
            desc_elem = soup.find('div', class_='woocommerce-product-details__short-description')
            if desc_elem:
                product_data['short_description'] = normalize_text(desc_elem.text)

            long_desc_elem = soup.find('div', id='tab-description') or \
                             soup.find('div', class_='woocommerce-product-details__long-description') or \
                             soup.find('div', class_='woocommerce-Tabs-panel--description')
            if long_desc_elem:
                product_data['description'] = normalize_text(long_desc_elem.text)
            elif desc_elem:
                product_data['description'] = normalize_text(desc_elem.text)

            # SKU
            sku_elem = soup.find('span', class_='sku')
            if sku_elem:
                product_data['sku'] = normalize_text(sku_elem.text)

            # Stock
            stock_elem = soup.find('p', class_='stock') or soup.find('span', class_='stock')
            page_text = _to_ascii_digits(soup.get_text(' ', strip=True))
            if stock_elem:
                stock_text = normalize_text(stock_elem.text)
                in_stock_marker = 'in stock' in (stock_text or '').lower() or 'স্টকে' in (stock_text or '')
                product_data['stock_status'] = 'in_stock' if in_stock_marker else 'out_of_stock'
            elif re.search(r'out of stock|স্টক শেষ', page_text, re.I):
                product_data['stock_status'] = 'out_of_stock'
            else:
                product_data['stock_status'] = 'in_stock'

            # Price fallback: any element showing "৪০৳" / "350.00৳" style text
            if not product_data.get('selling_price'):
                price_tag = soup.find(string=re.compile(r'\d+৳'))
                if price_tag:
                    price_val = normalize_price(price_tag.strip())
                    product_data['regular_price'] = price_val
                    product_data['selling_price'] = price_val

            # Product attributes (ISBN, pages, etc.)
            product_data.update(self._extract_attributes(soup))

            # Images from gallery + meta fallbacks
            product_data['images'] = self._extract_images(soup)

            # Author/Publisher/Categories from wafilife /cat/books/* links
            html_links = self._extract_cat_links(soup)
            if html_links['authors']:
                product_data.setdefault('authors', html_links['authors'])
            if html_links['publishers']:
                if not product_data.get('publisher'):
                    product_data['publisher'] = html_links['publishers'][0]
            if html_links['subjects']:
                product_data.setdefault('categories', html_links['subjects'])

            # Categories from WooCommerce breadcrumb (classic theme fallback)
            breadcrumb = soup.find('nav', class_='woocommerce-breadcrumb')
            if breadcrumb:
                categories = []
                home_markers = ('home', 'হোম', 'প্রচ্ছদ')
                for link in breadcrumb.find_all('a'):
                    text = normalize_text(link.text)
                    if text and text.lower() not in home_markers:
                        href = link.get('href')
                        if '/product-category/' in (href or ''):
                            categories.append({'name': text, 'url': href})
                if categories:
                    product_data['categories'] = categories

            return product_data

        except Exception as e:
            logger.error(f"Error extracting from HTML: {e}")
            return None

    def _extract_attributes(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract book-specific attributes from the attributes table"""
        attrs: Dict[str, Any] = {}

        attr_table = soup.find('table', class_='woocommerce-product-attributes')
        if not attr_table:
            return attrs

        for row in attr_table.find_all('tr'):
            label_elem = row.find('th')
            value_elem = row.find('td')
            if not (label_elem and value_elem):
                continue
            label = normalize_text(label_elem.text).lower()
            value = normalize_text(value_elem.text)
            if not value:
                continue

            if 'isbn' in label:
                attrs['isbn'] = value
            elif 'পৃষ্ঠা' in label or 'page' in label:
                try:
                    digits = re.sub(r'[^\d]', '', value)
                    if digits:
                        attrs['pages'] = int(digits)
                except ValueError:
                    pass
            elif 'cover' in label or 'বাঁধাই' in label:
                attrs['cover_type'] = value
            elif 'edition' in label or 'সংস্করণ' in label:
                attrs['edition'] = value
            elif 'year' in label or 'সাল' in label or 'প্রকাশনী সাল' in label:
                try:
                    digits = re.sub(r'[^\d]', '', value)
                    if len(digits) == 4:
                        attrs['published_year'] = int(digits)
                except ValueError:
                    pass
            elif 'language' in label or 'ভাষা' in label:
                attrs['language'] = value

        return attrs

    @staticmethod
    def _extract_images(soup: BeautifulSoup) -> list:
        """Extract image URLs: gallery first, then og/twitter meta fallbacks"""
        images = []

        gallery_elem = soup.find('div', class_='woocommerce-product-gallery') or \
                       soup.find('div', class_=re.compile('gallery|swiper'))
        if gallery_elem:
            seen_urls = set()
            for img in gallery_elem.find_all('img'):
                img_url = img.get('src') or img.get('data-large_image') or img.get('data-src')
                if img_url and img_url not in seen_urls and not img_url.startswith('data:'):
                    seen_urls.add(img_url)
                    images.append({
                        'url': img_url,
                        'is_main': len(images) == 0,
                        'sort_order': len(images)
                    })

        if not images:
            for prop in ('og:image', 'twitter:image', 'twitter:image:src'):
                meta = soup.find('meta', attrs={'property': prop}) or \
                       soup.find('meta', attrs={'name': prop})
                if meta and meta.get('content'):
                    images.append({'url': meta['content'], 'is_main': True, 'sort_order': 0})
                    break

        return images

    @staticmethod
    def _extract_cat_links(soup: BeautifulSoup) -> Dict[str, list]:
        """Extract author/publisher/subject links from wafilife /cat/books/* anchors"""
        skip_names = ('সবগুলো দেখুন', 'view all')
        authors, publishers, subjects = [], [], []
        seen = {'author': set(), 'publisher': set(), 'subject': set()}
        for a in soup.find_all('a', href=True):
            href = a['href'].split('?')[0]
            name = normalize_text(a.text)
            if not name or name.lower() in skip_names:
                continue
            if AUTHOR_HREF in href and name.lower() not in seen['author'] and href not in seen['author']:
                seen['author'].add(name.lower()); seen['author'].add(href)
                authors.append({'name': name, 'url': href})
            elif PUBLISHER_HREF in href and name.lower() not in seen['publisher'] and href not in seen['publisher']:
                seen['publisher'].add(name.lower()); seen['publisher'].add(href)
                publishers.append({'name': name, 'url': href})
            elif SUBJECT_HREF in href and name.lower() not in seen['subject'] and href not in seen['subject']:
                seen['subject'].add(name.lower()); seen['subject'].add(href)
                subjects.append({'name': name, 'url': href})
        return {'authors': authors, 'publishers': publishers, 'subjects': subjects}

    def _extract_categories_from_json_ld(self, json_ld: List[Dict]) -> List[Dict]:
        """Extract categories from breadcrumb JSON-LD"""
        categories = []

        for data in self._iter_json_ld(json_ld):
            if data.get('@type') == 'BreadcrumbList':
                items = data.get('itemListElement', [])
                for item in items:
                    entry = item.get('item') if isinstance(item.get('item'), dict) else item
                    name = normalize_text(entry.get('name'))
                    link = entry.get('@id') or entry.get('url')
                    if name and link and '/product-category/' in link:
                        categories.append({'name': name, 'url': link})
                break

        return categories

    @staticmethod
    def _iter_json_ld(json_ld: List[Any]):
        """Flatten nested JSON-LD graphs (@graph key)"""
        for data in json_ld:
            if not isinstance(data, dict):
                continue
            graph = data.get('@graph')
            if isinstance(graph, list):
                yield from graph
            yield data
