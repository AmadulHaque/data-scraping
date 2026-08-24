from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

from app.models.database import (
    Base, Product, Author, Publisher, Category,
    ProductImage, ProductMetadata, ScrapeURL, ScrapeRun, ScrapeError,
    product_authors, product_categories
)
from app.config import settings
from app.utils.normalizers import create_slug


class DatabaseRepository:
    def __init__(self):
        self.engine = create_engine(
            f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@"
            f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

    def create_tables(self):
        """Create all tables if they don't exist"""
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a database session"""
        return self.Session()

    def upsert_product(self, product_data: Dict[str, Any]):
        """Upsert product data - handle duplicates. Returns (id, operation)."""
        product_data = dict(product_data)  # avoid mutating caller's dict
        session = self.get_session()
        try:
            external_id = product_data.get('external_id')
            url = product_data.get('url')
            slug = product_data.get('slug')

            # Find existing product
            existing = None
            if external_id:
                existing = session.query(Product).filter_by(external_id=external_id).first()
            if not existing and url:
                existing = session.query(Product).filter_by(url=url).first()
            if not existing and slug:
                existing = session.query(Product).filter_by(slug=slug).first()

            # Process publisher
            publisher = product_data.pop('publisher', None)
            publisher_id = None
            if publisher and publisher.get('name'):
                publisher_id = self._get_or_create_publisher(session, publisher)

            # Process authors
            authors_data = product_data.pop('authors', [])
            author_ids = []
            for author_data in authors_data:
                author_id = self._get_or_create_author(session, author_data)
                if author_id:
                    author_ids.append(author_id)

            # Process categories
            categories_data = product_data.pop('categories', [])
            category_ids = []
            for category_data in categories_data:
                category_id = self._get_or_create_category(session, category_data)
                if category_id:
                    category_ids.append(category_id)

            # Process images and metadata (kept separate from scalar columns)
            images_data = product_data.pop('images', []) or []
            metadata_data = product_data.pop('metadata', []) or []

            # Strip relationship-only keys before setting scalars
            for key in list(product_data.keys()):
                if not hasattr(Product, key):
                    product_data.pop(key)

            # Remove identity keys - passed explicitly below
            product_data.pop('external_id', None)
            product_data.pop('url', None)
            product_data.pop('slug', None)

            # Create or update product
            if existing:
                for key, value in product_data.items():
                    if value is not None:
                        setattr(existing, key, value)
                existing.publisher_id = publisher_id
                existing.updated_at = datetime.utcnow()
                product = existing
                operation = 'updated'
            else:
                product = Product(
                    external_id=external_id or url,
                    url=url,
                    slug=slug,
                    publisher_id=publisher_id,
                    **product_data
                )
                session.add(product)
                session.flush()
                operation = 'new'

            # Handle relationships (always sync on update too)
            if author_ids:
                session.execute(
                    product_authors.delete().where(product_authors.c.product_id == product.id)
                )
                for author_id in author_ids:
                    session.execute(
                        product_authors.insert().values(
                            product_id=product.id, author_id=author_id
                        )
                    )

            if category_ids:
                session.execute(
                    product_categories.delete().where(product_categories.c.product_id == product.id)
                )
                for category_id in category_ids:
                    session.execute(
                        product_categories.insert().values(
                            product_id=product.id, category_id=category_id
                        )
                    )

            # Handle images
            if images_data:
                session.query(ProductImage).filter_by(product_id=product.id).delete()
                for img_data in images_data:
                    if not img_data.get('url'):
                        continue
                    session.add(ProductImage(
                        product_id=product.id,
                        url=img_data.get('url'),
                        thumbnail_url=img_data.get('thumbnail_url'),
                        is_main=img_data.get('is_main', False),
                        sort_order=img_data.get('sort_order', 0)
                    ))

            # Handle metadata
            if metadata_data:
                session.query(ProductMetadata).filter_by(product_id=product.id).delete()
                for meta_data in metadata_data:
                    if not meta_data.get('key'):
                        continue
                    session.add(ProductMetadata(
                        product_id=product.id,
                        key=str(meta_data.get('key')),
                        value=str(meta_data.get('value'))
                    ))

            session.commit()
            return product.id, operation

        except IntegrityError as e:
            session.rollback()
            logger.error(f"Integrity error upserting product: {e}")
            return None, 'error'
        except Exception as e:
            session.rollback()
            logger.error(f"Error upserting product: {e}")
            return None, 'error'
        finally:
            session.close()

    def _get_or_create_publisher(self, session: Session, publisher_data: Dict) -> Optional[int]:
        name = publisher_data.get('name')
        if not name:
            return None

        publisher = session.query(Publisher).filter_by(name=name).first()
        if not publisher:
            publisher = Publisher(
                name=name,
                url=publisher_data.get('url'),
                external_id=publisher_data.get('external_id'),
                slug=publisher_data.get('slug') or create_slug(name)
            )
            session.add(publisher)
            session.flush()

        return publisher.id

    def _get_or_create_author(self, session: Session, author_data: Dict) -> Optional[int]:
        name = author_data.get('name')
        if not name:
            return None

        author = session.query(Author).filter_by(name=name).first()
        if not author:
            slug = create_slug(name)
            author = Author(
                name=name,
                url=author_data.get('url'),
                external_id=author_data.get('external_id'),
                slug=author_data.get('slug') or slug
            )
            session.add(author)
            session.flush()

        return author.id

    def _get_or_create_category(self, session: Session, category_data: Dict) -> Optional[int]:
        name = category_data.get('name')
        if not name:
            return None

        category = session.query(Category).filter_by(name=name).first()
        if not category:
            slug = create_slug(name)
            category = Category(
                name=name,
                url=category_data.get('url'),
                external_id=category_data.get('external_id'),
                slug=category_data.get('slug') or slug,
            )
            parent_name = (category_data.get('parent') or {}).get('name')
            if parent_name:
                parent_id = self._get_or_create_category(
                    session, category_data['parent']
                )
                if parent_id:
                    category.parent_id = parent_id
            session.add(category)
            session.flush()

        return category.id

    # ---- URL queue management ----

    def add_scrape_url(self, url: str, url_type: str = 'product') -> bool:
        """Add URL to scrape queue"""
        session = self.get_session()
        try:
            exists = session.query(ScrapeURL).filter_by(url=url).first()
            if exists:
                return False

            session.add(ScrapeURL(url=url, url_type=url_type, status='pending'))
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error adding scrape URL: {e}")
            return False
        finally:
            session.close()

    def get_pending_urls(self, limit: int = 100) -> List[ScrapeURL]:
        session = self.get_session()
        try:
            return session.query(ScrapeURL).filter_by(status='pending').limit(limit).all()
        finally:
            session.close()

    def get_failed_urls(self, limit: int = 1000) -> List[ScrapeURL]:
        """Get failed URLs eligible for retry (attempts < max_attempts)"""
        session = self.get_session()
        try:
            return (
                session.query(ScrapeURL)
                .filter(
                    ScrapeURL.status == 'failed',
                    ScrapeURL.attempts < ScrapeURL.max_attempts
                )
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def reset_url_for_retry(self, url_id: int):
        """Reset a failed URL back to pending"""
        session = self.get_session()
        try:
            scrape_url = session.query(ScrapeURL).filter_by(id=url_id).first()
            if scrape_url:
                scrape_url.status = 'pending'
                scrape_url.last_error = None
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error resetting URL {url_id}: {e}")
            return False
        finally:
            session.close()

    def update_url_status(self, url_id: int, status: str, error: Optional[str] = None):
        """Update URL processing status"""
        session = self.get_session()
        try:
            scrape_url = session.query(ScrapeURL).filter_by(id=url_id).first()
            if scrape_url:
                scrape_url.status = status
                scrape_url.attempts += 1
                if error:
                    scrape_url.last_error = error
                scrape_url.last_attempt_at = datetime.utcnow()
                if status == 'completed':
                    scrape_url.completed_at = datetime.utcnow()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating URL status: {e}")
        finally:
            session.close()

    # ---- Scrape runs & errors ----

    def create_scrape_run(self, config: Optional[Dict] = None) -> Optional[str]:
        session = self.get_session()
        try:
            run = ScrapeRun(config=config)
            session.add(run)
            session.commit()
            return run.run_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating scrape run: {e}")
            return None
        finally:
            session.close()

    def update_scrape_run(self, run_id: str, stats: Dict):
        session = self.get_session()
        try:
            run = session.query(ScrapeRun).filter_by(run_id=run_id).first()
            if run:
                for key, value in stats.items():
                    if hasattr(run, key):
                        setattr(run, key, value)
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating scrape run: {e}")
        finally:
            session.close()

    def log_error(self, error_data: Dict):
        session = self.get_session()
        try:
            session.add(ScrapeError(**{
                k: v for k, v in error_data.items() if hasattr(ScrapeError, k)
            }))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error logging error: {e}")
        finally:
            session.close()

    # ---- Export helpers ----

    def get_products_for_export(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch recently scraped products with relationships as plain dicts"""
        session = self.get_session()
        try:
            products = (
                session.query(Product)
                .filter(Product.last_scraped_at.isnot(None))
                .order_by(Product.last_scraped_at.desc())
                .limit(limit)
                .all()
            )
            return [self._product_to_dict(p) for p in products]
        finally:
            session.close()

    @staticmethod
    def _product_to_dict(p: Product) -> Dict[str, Any]:
        return {
            'external_id': p.external_id,
            'name': p.name,
            'slug': p.slug,
            'url': p.url,
            'description': p.description,
            'short_description': p.short_description,
            'sku': p.sku,
            'isbn': p.isbn,
            'regular_price': p.regular_price,
            'selling_price': p.selling_price,
            'discount': p.discount,
            'stock_status': p.stock_status,
            'pages': p.pages,
            'cover_type': p.cover_type,
            'edition': p.edition,
            'published_year': p.published_year,
            'language': p.language,
            'authors': [{'name': a.name, 'url': a.url} for a in p.authors],
            'publisher': {'name': p.publisher.name, 'url': p.publisher.url} if p.publisher else None,
            'categories': [{'name': c.name, 'url': c.url} for c in p.categories],
            'images': [
                {
                    'url': i.url,
                    'thumbnail_url': i.thumbnail_url,
                    'is_main': i.is_main,
                    'sort_order': i.sort_order,
                }
                for i in sorted(p.images, key=lambda x: x.sort_order)
            ],
            'metadata': [{'key': m.key, 'value': m.value} for m in p.meta],
            'content_hash': p.content_hash,
            'last_scraped_at': p.last_scraped_at.isoformat() if p.last_scraped_at else None,
        }
