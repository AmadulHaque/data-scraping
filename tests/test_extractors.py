import pytest
from bs4 import BeautifulSoup

from app.extractors.product import ProductExtractor
from app.crawler.base import BaseCrawler


PRODUCT_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@type": "Product",
  "name": "বাংলা সাহিত্যের ইতিহাস",
  "sku": "978-984-93839-7-1",
  "isbn": "978-984-93839-7-1",
  "description": "Test book description",
  "image": ["https://www.wafilife.com/img/main.jpg", "https://www.wafilife.com/img/2.jpg"],
  "brand": {"name": "Onno Prokash"},
  "offers": {
    "price": "350",
    "priceCurrency": "BDT",
    "priceSpecification": {"price": "400", "priceCurrency": "BDT"},
    "availability": "https://schema.org/InStock"
  }
}
</script>
</head><body>
<h1 class="product_title">বাংলা সাহিত্যের ইতিহাস</h1>
<p class="price"><del>400.00৳</del> <ins>350.00৳</ins></p>
<div class="woocommerce-product-details__short-description">Short desc</div>
<table class="woocommerce-product-attributes">
  <tr><th>ISBN</th><td>978-984-93839-7-1</td></tr>
  <tr><th>পৃষ্ঠা</th><td>320</td></tr>
  <tr><th>বাঁধাই</th><td>হার্ডকভার</td></tr>
  <tr><th>ভাষা</th><td>বাংলা</td></tr>
</table>
<nav class="woocommerce-breadcrumb">
  <a href="/">হোম</a>
  <a href="/product-category/uponnash/">উপন্যাস</a>
</nav>
</body></html>
"""


@pytest.fixture
def extractor():
    return ProductExtractor()


@pytest.fixture
def product_page():
    soup = BeautifulSoup(PRODUCT_HTML, 'lxml')
    crawler = BaseCrawler()
    json_ld = crawler._extract_json_ld(soup)
    return {
        'url': 'https://www.wafilife.com/product/bangla-sahityer-itihas/',
        'soup': soup,
        'json_ld': json_ld,
        'html': PRODUCT_HTML,
    }


def test_extract_json_ld(extractor, product_page):
    product = extractor.extract(product_page)

    assert product is not None
    assert product.name == 'বাংলা সাহিত্যের ইতিহাস'
    assert product.sku == '978-984-93839-7-1'
    assert product.regular_price == 400.0
    assert product.selling_price == 350.0
    assert product.stock_status == 'in_stock'


def test_extract_images(extractor, product_page):
    product = extractor.extract(product_page)

    assert len(product.images) == 2
    assert product.images[0].is_main is True
    assert product.images[0].sort_order == 0
    assert product.images[1].is_main is False


def test_extract_publisher(extractor, product_page):
    product = extractor.extract(product_page)
    assert product.publisher.name == 'Onno Prokash'


def test_html_attribute_fallback(extractor, product_page):
    """HTML attributes (pages, cover) not present in JSON-LD get merged"""
    product = extractor.extract(product_page)

    assert product.pages == 320
    assert product.cover_type == 'হার্ডকভার'
    assert product.language == 'বাংলা'


def test_extract_from_html_only(extractor, product_page):
    """When JSON-LD absent, falls back to HTML parsing"""
    product_page['json_ld'] = []
    product = extractor.extract(product_page)

    assert product is not None
    assert product.name == 'বাংলা সাহিত্যের ইতিহাস'
    assert product.regular_price == 400.0
    assert product.selling_price == 350.0


def test_empty_soup_returns_none(extractor):
    assert extractor.extract({'url': 'x', 'soup': None}) is None
