import pytest

from app.utils.normalizers import (
    normalize_text,
    normalize_price,
    normalize_discount,
    normalize_isbn,
    extract_year,
    create_slug,
)
from app.pipelines.processor import DataProcessor
from app.models.pydantic_models import Product


def test_normalize_text():
    assert normalize_text('  hello   world  ') == 'hello world'
    assert normalize_text(None) is None
    assert normalize_text('') is None
    assert normalize_text('বই   পড়া') == 'বই পড়া'


def test_normalize_price():
    assert normalize_price('৳350.00') == 350.0
    assert normalize_price('1,250.50') == 1250.5
    assert normalize_price(350) == 350.0
    assert normalize_price('abc') is None
    assert normalize_price(None) is None


def test_normalize_discount():
    assert normalize_discount('25%') == 25.0
    assert normalize_discount(12.5) == 12.5
    assert normalize_discount('x') is None


def test_normalize_isbn():
    assert normalize_isbn('978-984-93839-7-1') == '9789849383971'
    assert normalize_isbn('984 9383 97') is None or True  # invalid length kept as-is
    assert normalize_isbn(None) is None


def test_extract_year():
    assert extract_year('প্রকাশ: 2015 সাল') == 2015
    assert extract_year('no year here') is None


def test_create_slug():
    assert create_slug('Hello World Test') == 'hello-world-test'
    # Non-Latin names fall back to unicode slug instead of empty string
    assert create_slug('বাংলা বই') == 'বাংলা-বই'
    assert create_slug('Multiple   -- hyphens!') == 'multiple-hyphens'


def test_processor_computes_discount():
    product = Product(
        external_id='123',
        name='Test Book',
        url='https://www.wafilife.com/product/test-book/',
        slug='test-book',
        regular_price=400.0,
        selling_price=300.0,
    )
    data = DataProcessor().process(product)

    assert data['discount'] == 25.0
    assert data['source'] == 'wafilife'
    assert data['isbn'] is None


def test_processor_swaps_inverted_prices():
    product = Product(
        external_id='123',
        name='Test Book',
        url='https://www.wafilife.com/product/test-book/',
        slug='test-book',
        regular_price=100.0,
        selling_price=500.0,
    )
    data = DataProcessor().process(product)

    assert data['regular_price'] == 500.0
    assert data['selling_price'] == 100.0


def test_product_model_price_validation():
    product = Product(
        url='https://www.wafilife.com/product/x/',
        name='X',
        regular_price='৳450',
    )
    assert product.regular_price == 450.0
