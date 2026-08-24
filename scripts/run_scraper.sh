#!/bin/bash
# Run the wafilife scraper end-to-end
set -e

LIMIT="${1:-0}"

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "No .env found, copying .env.example"
    cp .env.example .env
fi

mkdir -p logs exports

echo "=== Discovering URLs ==="
python main.py discover

echo "=== Scraping products ==="
python main.py scrape --limit "$LIMIT"

echo "=== Done. Exports in ./exports ==="
