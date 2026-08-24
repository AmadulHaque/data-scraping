import asyncio
import re
from typing import List, Set, Optional
from urllib.parse import urljoin, urlparse
from loguru import logger
import xml.etree.ElementTree as ET

from app.crawler.base import BaseCrawler
from app.crawler.pagination import PaginationHandler
from app.config import settings

NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


def _tag(el) -> str:
    return el.tag.split('}')[-1]


class URLDiscovery:
    """Discover product and category URLs from sitemap and category pages"""

    def __init__(self):
        self.base_url = settings.BASE_URL
        self.sitemap_url = settings.SITEMAP_URL
        self.pagination = PaginationHandler()
        self.concurrency = settings.MAX_CONCURRENCY
        self.delay = settings.REQUEST_DELAY

    async def discover_from_sitemap(self) -> List[str]:
        """Parse product sitemap shards for /product/ URLs"""
        product_urls: Set[str] = set()

        async with BaseCrawler() as crawler:
            all_locs = await self._get_sitemap_locations(crawler, self.sitemap_url)
            # Only product shards - skip static/writers/categories shards
            product_shards = [
                loc for loc in all_locs
                if re.search(r'sitemap-products', urlparse(loc).path)
            ]
            logger.info(f"Fetching {len(product_shards)} product sitemap shards")

            sem = asyncio.Semaphore(self.concurrency)

            async def fetch_shard(loc: str):
                async with sem:
                    try:
                        urls = await self._parse_sitemap(crawler, loc)
                        await asyncio.sleep(self.delay)
                        return urls
                    except Exception as e:
                        logger.warning(f"Failed to parse sitemap {loc}: {e}")
                        return []

            results = await asyncio.gather(*[fetch_shard(l) for l in product_shards])

            for urls in results:
                product_urls.update(
                    u for u in urls
                    if settings.PRODUCT_URL_PATTERN in urlparse(u).path
                )

        logger.info(f"Sitemap discovery found {len(product_urls)} product URLs")
        return list(product_urls)

    async def discover_from_categories(self) -> List[str]:
        """Crawl category pages (BFS, max 2 levels) for product URLs"""
        product_urls: Set[str] = set()

        async with BaseCrawler() as crawler:
            frontier = await self._get_category_urls(crawler)
            logger.info(f"Found {len(frontier)} category pages to crawl")
            visited: Set[str] = set()

            for depth in range(2):  # root -> leaf
                next_frontier: List[str] = []
                for cat_url in frontier[:200]:  # safety cap per level
                    if cat_url in visited:
                        continue
                    visited.add(cat_url)
                    try:
                        page_data = await crawler.fetch(cat_url)
                        if not page_data:
                            continue

                        found = self._extract_product_links(page_data['soup'], base=cat_url)
                        product_urls.update(found)

                        # Deeper category links on index pages
                        if not found:
                            for a in page_data['soup'].find_all('a', href=True):
                                href = urljoin(cat_url, a['href']).split('?')[0]
                                path = urlparse(href).path
                                if '/cat/' in path and href not in visited:
                                    next_frontier.append(href)

                        await asyncio.sleep(self.delay)
                    except Exception as e:
                        logger.warning(f"Error crawling category {cat_url}: {e}")

                if not next_frontier:
                    break
                frontier = list(dict.fromkeys(next_frontier))
                logger.info(f"Category level {depth + 2}: {len(frontier)} pages")

        logger.info(f"Category discovery found {len(product_urls)} product URLs")
        return list(product_urls)

    async def _get_sitemap_locations(self, crawler: BaseCrawler, sitemap_url: str) -> List[str]:
        """Get sub-sitemap locations. Handles both index and plain sitemaps."""
        try:
            response = await crawler.session.get(sitemap_url)
            response.raise_for_status()
            root = ET.fromstring(response.content)

            if _tag(root) == 'sitemapindex':
                return [
                    loc.text.strip()
                    for loc in root.findall('.//sm:sitemap/sm:loc', NS)
                    if loc.text
                ]

            # Plain sitemap with URL entries - return the original URL
            if root.findall('.//sm:url', NS):
                return [sitemap_url]

            return []
        except Exception as e:
            logger.error(f"Error fetching sitemap {sitemap_url}: {e}")
            return []

    async def _parse_sitemap(self, crawler: BaseCrawler, sitemap_url: str) -> List[str]:
        """Extract all <loc> URLs from a single sitemap"""
        response = await crawler.session.get(sitemap_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        return [
            loc.text.strip()
            for loc in root.findall('.//sm:url/sm:loc', NS)
            if loc.text
        ]

    async def _get_category_urls(self, crawler: BaseCrawler) -> List[str]:
        """Get /product-category/ URLs directly from category sitemap shards"""
        category_urls: Set[str] = set()

        all_locs = await self._get_sitemap_locations(crawler, self.sitemap_url)
        category_shards = [
            loc for loc in all_locs
            if re.search(r'sitemap-categories', urlparse(loc).path)
        ]

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_shard(loc: str):
            async with sem:
                try:
                    urls = await self._parse_sitemap(crawler, loc)
                    await asyncio.sleep(self.delay)
                    return urls
                except Exception as e:
                    logger.warning(f"Failed to parse sitemap {loc}: {e}")
                    return []

        results = await asyncio.gather(*[fetch_shard(l) for l in category_shards])
        for urls in results:
            for u in urls:
                path = urlparse(u).path
                # Keep only leaf-ish categories: /cat/books/{type}/{slug}
                if '/cat/' in path and path.rstrip('/').count('/') <= 4:
                    category_urls.add(u)

        return list(category_urls)

    def _extract_product_links(self, soup, base: str) -> Set[str]:
        """Extract absolute /product/ links from a page"""
        links: Set[str] = set()
        for a in soup.find_all('a', href=True):
            href = urljoin(base, a['href'])
            parsed = urlparse(href)
            if settings.PRODUCT_URL_PATTERN in parsed.path:
                links.add(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
        return links
