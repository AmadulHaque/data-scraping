import asyncio
from typing import Optional
from urllib.parse import urlencode, urlunparse, urlparse, parse_qs
from loguru import logger


class PaginationHandler:
    """Handle category pagination via ?page={n} parameter"""

    def __init__(self):
        from app.config import settings
        self.request_delay = settings.REQUEST_DELAY

    @staticmethod
    def build_page_url(url: str, page: int) -> str:
        """Add or replace ?page={n} query parameter"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params['page'] = [str(page)]
        query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=query))

    @staticmethod
    def detect_total_pages(soup) -> Optional[int]:
        """Detect total number of pages from pagination markup.

        Supports WooCommerce (.page-numbers) and rc-pagination
        (wafilife custom theme). Returns None when no pagination present.
        """
        nav = soup.find('nav', class_='woocommerce-pagination') or \
              soup.find('ul', class_='page-numbers') or \
              soup.find(class_=lambda c: c and 'rc-pagination' in ' '.join(c))
        if not nav:
            return None

        max_page = 1
        # WooCommerce style links/spans + rc-pagination items
        for el in nav.find_all(['a', 'span', 'li', 'button']):
            text = el.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))

        # Fallback: use next link's target page number
        next_link = nav.find('a', class_='next') or nav.find('button', class_='rc-pagination-next')
        if next_link is not None:
            href = next_link.get('href', '')
            for num in parse_qs(urlparse(href).query).get('page', []):
                if num.isdigit():
                    max_page = max(max_page, int(num))

        return max_page if max_page > 1 else 1

    @staticmethod
    def has_next_page(soup) -> bool:
        """Check if a next-page link exists"""
        return soup.find('a', class_='next') is not None or \
               soup.find('span', class_='next') is not None

    async def crawl_pages(self, crawler, start_url: str, callback):
        """Iterate all paginated pages of a listing URL, invoking callback(soup, url)"""
        page = 1
        while True:
            page_url = self.build_page_url(start_url, page)
            try:
                page_data = await crawler.fetch(page_url)
                if not page_data:
                    break

                await callback(page_data['soup'], page_url)

                total = self.detect_total_pages(page_data['soup'])
                if total and page >= total:
                    break
                if total is None:
                    break

                page += 1
                await asyncio.sleep(self.request_delay)
            except Exception as e:
                logger.error(f"Pagination error on {page_url}: {e}")
                break
