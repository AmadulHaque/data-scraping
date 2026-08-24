import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Optional

import httpx
from loguru import logger

from app.config import settings


class ImageDownloader:
    """Download product images from scraped image URLs to local disk"""

    IMAGE_EXT_RE = re.compile(r'\.(jpe?g|png|gif|webp)(?:[?#].*)?$', re.I)

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.path.join(settings.EXPORT_DIR, 'images'))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.concurrency = settings.MAX_CONCURRENCY

    async def download_product_images(
        self, client: httpx.AsyncClient, slug: str, images: List[Dict]
    ) -> List[str]:
        """Download all images for one product into base_dir/{slug}/. Returns saved paths."""
        if not images:
            return []

        product_dir = self.base_dir / self._safe_name(slug)
        product_dir.mkdir(parents=True, exist_ok=True)
        saved: List[str] = []

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch(image: Dict):
            url = image.get('url') or ''
            if not url or 'placeholder' in url.lower():
                return None
            async with sem:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    path = product_dir / self._filename(url, image, len(saved))
                    path.write_bytes(resp.content)
                    await asyncio.sleep(settings.REQUEST_DELAY)
                    return str(path)
                except Exception as e:
                    logger.warning(f"Image download failed {url}: {e}")
                    return None

        results = await asyncio.gather(*[fetch(img) for img in images])
        saved = [r for r in results if r]

        if saved:
            logger.debug(f"Saved {len(saved)} images for {slug}")
        return saved

    @staticmethod
    def _safe_name(name: str) -> str:
        name = re.sub(r'[^\w\u0980-\u09FF-]', '_', name.strip())
        return name[:120] or 'unnamed'

    def _filename(self, url: str, image: Dict, index: int) -> str:
        prefix = 'main' if image.get('is_main') else f'{image.get("sort_order", index):02d}'
        ext_match = self.IMAGE_EXT_RE.search(urlparse(url).path or url)
        ext = ext_match.group(1).lower() if ext_match else 'jpg'
        return f'{prefix}.{ext}'

    async def download_all(self, products: List[Dict]) -> Dict[str, List[str]]:
        """Download images for a list of product dicts (as returned by export).

        Returns mapping slug -> saved file paths.
        """
        results: Dict[str, List[str]] = {}
        timeout = httpx.Timeout(settings.REQUEST_TIMEOUT)

        async with httpx.AsyncClient(
            headers={'User-Agent': settings.USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            for product in products:
                slug = product.get('slug') or self._safe_name(product.get('name') or 'unnamed')
                images = product.get('images') or []
                if not images:
                    continue
                saved = await self.download_product_images(client, slug, images)
                if saved:
                    results[slug] = saved

        logger.info(f"Downloaded images for {len(results)}/{len(products)} products")
        return results
