import asyncio
import httpx
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from loguru import logger
import hashlib
import json

from app.config import settings
from app.utils.retry import retry_with_backoff


class BaseCrawler:
    def __init__(self):
        self.session = None
        self.user_agent = settings.USER_AGENT
        self.timeout = settings.REQUEST_TIMEOUT
        self.delay = settings.REQUEST_DELAY

    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            headers={
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
                # NB: don't set Accept-Encoding manually - httpx negotiates
                # only encodings it can decode (brotli needs Brotli pkg)
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
            },
            follow_redirects=True,
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    @retry_with_backoff(max_retries=settings.MAX_RETRIES)
    async def fetch(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch URL with retry logic"""
        try:
            response = await self.session.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')
            json_ld = self._extract_json_ld(soup)

            return {
                'url': url,
                'status_code': response.status_code,
                'html': response.text,
                'soup': soup,
                'json_ld': json_ld
            }
        except httpx.TimeoutException as e:
            logger.error(f"Timeout fetching {url}: {e}")
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"404 Not found: {url}")
                return None
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise

    def _extract_json_ld(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract JSON-LD from HTML"""
        json_ld_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string or '')
                json_ld_data.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return json_ld_data

    def compute_hash(self, data: Dict) -> str:
        """Compute content hash for duplicate detection"""
        stable_data = {
            k: v for k, v in data.items()
            if k not in ['last_scraped_at', 'content_hash']
        }
        json_str = json.dumps(stable_data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
