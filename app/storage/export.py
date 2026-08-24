import json
import os
from datetime import datetime
from typing import List, Dict, Any
from loguru import logger

from app.config import settings


class JSONExporter:
    """Export scraped products to JSON or JSONL files"""

    def __init__(self, export_dir: str = None):
        self.export_dir = export_dir or settings.EXPORT_DIR
        os.makedirs(self.export_dir, exist_ok=True)

    def export_products(self, products: List[Dict[str, Any]], format: str = 'jsonl') -> str:
        """Export products to file. Returns output path."""
        if not products:
            logger.warning("No products to export")
            return ''

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format == 'jsonl':
            path = os.path.join(self.export_dir, f'products_{timestamp}.jsonl')
            self._export_jsonl(products, path)
        elif format == 'json':
            path = os.path.join(self.export_dir, f'products_{timestamp}.json')
            self._export_json(products, path)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"Exported {len(products)} products to {path}")
        return path

    def _export_jsonl(self, products: List[Dict[str, Any]], path: str):
        with open(path, 'w', encoding='utf-8') as f:
            for product in products:
                f.write(json.dumps(product, ensure_ascii=False, default=str) + '\n')

    def _export_json(self, products: List[Dict[str, Any]], path: str):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2, default=str)
