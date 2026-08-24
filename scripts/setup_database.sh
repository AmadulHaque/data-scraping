#!/bin/bash
# Setup PostgreSQL database for wafilife scraper
set -e

DB_NAME="${DB_NAME:-wafilife}"
DB_USER="${DB_USER:-wafilife}"
DB_PASSWORD="${DB_PASSWORD:-wafilife}"
DB_HOST="${DB_HOST:-localhost}"
# Admin account used to bootstrap. Defaults to current macOS/Linux user,
# override with ADMIN_USER / ADMIN_PASSWORD if different.
ADMIN_USER="${ADMIN_USER:-$(whoami)}"

PSQL_ADMIN="psql -h ${DB_HOST} -U ${ADMIN_USER}"

echo "Using admin role: ${ADMIN_USER}"

echo "Creating user ${DB_USER} (if missing)..."
${PSQL_ADMIN} postgres -c "DO \$\$ BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
      CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
   END IF;
END \$\$;"

echo "Creating database ${DB_NAME} (if missing)..."
if ! ${PSQL_ADMIN} postgres -tc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1; then
    ${PSQL_ADMIN} postgres -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
fi

# Postgres 15+: non-owner roles cannot create tables in schema public by default
echo "Granting schema permissions to ${DB_USER}..."
${PSQL_ADMIN} "${DB_NAME}" -c "GRANT ALL ON SCHEMA public TO ${DB_USER};"

echo "Applying migrations..."
for migration in migrations/*.sql; do
    echo "  -> ${migration}"
    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -f "${migration}"
done

echo "Database setup complete."
