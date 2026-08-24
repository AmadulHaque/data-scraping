import asyncio
import click
from loguru import logger
import time
from datetime import datetime

from app.config import settings
from app.crawler.base import BaseCrawler
from app.crawler.discovery import URLDiscovery
from app.extractors.product import ProductExtractor
from app.pipelines.processor import DataProcessor
from app.storage.postgres import DatabaseRepository
from app.storage.export import JSONExporter
from app.utils.logging import setup_logging

# Setup logging
setup_logging()


class WafilifeScraper:
    def __init__(self):
        self.db = DatabaseRepository()
        self.discovery = URLDiscovery()
        self.extractor = ProductExtractor()
        self.processor = DataProcessor()
        self.exporter = JSONExporter()

        self.db.create_tables()

        self.run_id = None
        self.stats = {
            'total_urls_discovered': 0,
            'total_products_processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'updated': 0,
            'new_products': 0,
            'duplicates': 0,
            'avg_response_time': 0,
        }
        self.start_time = None
        self.end_time = None

    async def run_discovery(self):
        """Discover product URLs"""
        logger.info("Starting URL discovery...")

        # Discover from sitemap
        sitemap_urls = await self.discovery.discover_from_sitemap()
        logger.info(f"Discovered {len(sitemap_urls)} URLs from sitemap")

        # Discover from categories
        category_urls = await self.discovery.discover_from_categories()
        logger.info(f"Discovered {len(category_urls)} URLs from categories")

        # Combine and deduplicate
        all_urls = list(set(sitemap_urls + category_urls))
        logger.info(f"Total unique URLs discovered: {len(all_urls)}")

        # Store in database
        added_count = 0
        for url in all_urls:
            if self.db.add_scrape_url(url, 'product'):
                added_count += 1

        self.stats['total_urls_discovered'] = added_count
        logger.info(f"Added {added_count} URLs to scrape queue")

        return all_urls

    async def run_scrape(self, limit: int = 0):
        """Run the scraping process"""
        self.start_time = time.time()
        self.run_id = self.db.create_scrape_run(config={
            'test_mode': settings.TEST_MODE,
            'max_products': settings.MAX_PRODUCTS,
            'limit': limit,
        })

        if not self.run_id:
            logger.error("Failed to create scrape run")
            return

        logger.info(f"Starting scrape run {self.run_id}")

        # Get URLs to scrape
        pending_urls = self.db.get_pending_urls(limit if limit > 0 else 1000)
        total_urls = len(pending_urls)

        logger.info(f"Processing {total_urls} URLs")

        # Process URLs
        async with BaseCrawler() as crawler:
            for idx, url_record in enumerate(pending_urls):
                if settings.TEST_MODE and idx >= settings.MAX_PRODUCTS:
                    break

                try:
                    # Update status
                    self.db.update_url_status(url_record.id, 'processing')

                    # Fetch page
                    page_data = await crawler.fetch(url_record.url)

                    if not page_data:
                        self.db.update_url_status(url_record.id, 'failed', 'No data received')
                        self.stats['failed'] += 1
                        continue

                    # Extract product data
                    product_data = self.extractor.extract(page_data)

                    if not product_data:
                        self.db.update_url_status(url_record.id, 'failed', 'No product data extracted')
                        self.stats['failed'] += 1
                        continue

                    # Process and normalize
                    processed_data = self.processor.process(product_data)

                    # Compute content hash
                    content_hash = crawler.compute_hash(processed_data)
                    processed_data['content_hash'] = content_hash
                    processed_data['last_scraped_at'] = datetime.utcnow()

                    # Save to database
                    product_id, operation = self.db.upsert_product(processed_data)

                    if product_id:
                        self.db.update_url_status(url_record.id, 'completed')
                        self.stats['successful'] += 1

                        if operation == 'new':
                            self.stats['new_products'] += 1
                        elif operation == 'updated':
                            self.stats['updated'] += 1
                    else:
                        self.db.update_url_status(url_record.id, 'failed', 'Database error')
                        self.stats['failed'] += 1

                    self.stats['total_products_processed'] += 1

                    # Log progress
                    if (idx + 1) % 100 == 0:
                        logger.info(f"Processed {idx + 1}/{total_urls} URLs")

                except Exception as e:
                    logger.error(f"Error processing {url_record.url}: {e}")
                    self.db.update_url_status(url_record.id, 'failed', str(e))
                    self.db.log_error({
                        'url': url_record.url,
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'run_id': self.run_id,
                    })
                    self.stats['failed'] += 1

        self.end_time = time.time()
        self._finalize_run()

        # Export data
        await self.export_results()

        # Print summary
        self.print_summary()

    async def retry_failed(self):
        """Retry previously failed URLs"""
        failed = self.db.get_failed_urls(limit=1000)
        logger.info(f"Found {len(failed)} failed URLs eligible for retry")

        for url_record in failed:
            self.db.reset_url_for_retry(url_record.id)

        if failed:
            await self.run_scrape(limit=len(failed))

    def _finalize_run(self):
        """Finalize the scrape run"""
        execution_time = (self.end_time or time.time()) - (self.start_time or time.time())
        self.stats['total_execution_time'] = execution_time
        self.stats['avg_response_time'] = execution_time / max(self.stats['total_products_processed'], 1)

        self.db.update_scrape_run(self.run_id, self.stats)
        logger.info(f"Scrape run {self.run_id} completed")

    async def export_results(self):
        """Export results to JSON/JSONL"""
        logger.info("Exporting results...")

        products = self.db.get_products_for_export(limit=settings.SCRAPE_BATCH_SIZE * 10)

        if products:
            self.exporter.export_products(products, format=settings.EXPORT_FORMAT)
            logger.info(f"Exported {len(products)} products to {settings.EXPORT_DIR}")

    def print_summary(self):
        """Print summary statistics"""
        logger.info("=" * 60)
        logger.info("SCRAPING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Run ID: {self.run_id}")
        logger.info(f"Total URLs Discovered: {self.stats['total_urls_discovered']}")
        logger.info(f"Total Products Processed: {self.stats['total_products_processed']}")
        logger.info(f"Successful: {self.stats['successful']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Skipped: {self.stats['skipped']}")
        logger.info(f"New Products: {self.stats['new_products']}")
        logger.info(f"Updated Products: {self.stats['updated']}")
        logger.info(f"Duplicates: {self.stats['duplicates']}")
        logger.info(f"Average Response Time: {self.stats['avg_response_time']:.2f}s")
        if self.stats.get('total_execution_time'):
            logger.info(f"Total Execution Time: {self.stats['total_execution_time']:.2f}s")
        logger.info("=" * 60)


@click.group()
def cli():
    """Wafilife.com Product Scraper"""
    pass


@cli.command()
def discover():
    """Discover product URLs"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.run_discovery())


@cli.command()
@click.option('--limit', default=0, help='Limit number of products to scrape')
def scrape(limit):
    """Scrape products"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.run_scrape(limit))


@cli.command()
@click.option('--format', default='jsonl', help='Export format (json, jsonl)')
def export(format):
    """Export scraped data"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.export_results())


@cli.command()
def stats():
    """Show scraping statistics from last run"""
    scraper = WafilifeScraper()
    session = scraper.db.get_session()
    try:
        from app.models.database import ScrapeRun
        run = session.query(ScrapeRun).order_by(ScrapeRun.id.desc()).first()
        if not run:
            logger.warning("No scrape runs found")
            return
        scraper.run_id = run.run_id
        for field in ('total_urls_discovered', 'total_products_processed', 'successful',
                      'failed', 'skipped', 'new_products', 'updated',
                      'duplicates', 'avg_response_time', 'total_execution_time'):
            scraper.stats[field] = getattr(run, field, 0) or 0
        scraper.print_summary()
    finally:
        session.close()


@cli.command()
@click.option('--limit', default=0, help='Limit number of products (0 = all with images)')
@click.option('--dir', 'out_dir', default=None, help='Image output directory')
def images(limit, out_dir):
    """Download product images to disk"""
    from app.storage.image_downloader import ImageDownloader

    scraper = WafilifeScraper()
    products = scraper.db.get_products_for_export(
        limit=limit if limit > 0 else 100000
    )
    with_images = [p for p in products if p.get('images')]
    logger.info(f"{len(with_images)} products with images")

    downloader = ImageDownloader(base_dir=out_dir)
    results = asyncio.run(downloader.download_all(with_images))

    total_files = sum(len(v) for v in results.values())
    logger.info(f"Saved {total_files} image files for {len(results)} products")


@cli.command()
def retry_failed():
    """Retry failed URLs"""
    scraper = WafilifeScraper()
    asyncio.run(scraper.retry_failed())


if __name__ == '__main__':
    cli()
