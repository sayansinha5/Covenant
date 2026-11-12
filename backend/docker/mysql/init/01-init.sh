#!/bin/bash
# Runs once, on the first start of an empty mysql_data volume.
# Creates the app and test databases, a migrator user with DDL rights (Alembic only) and an app
# user with schema-wide SELECT only. Table-level INSERT/UPDATE/DELETE grants for the app user are
# applied by the Alembic environment after every upgrade, which is how ledger_entries stays
# INSERT/SELECT only.
set -euo pipefail

: "${DB_NAME:?DB_NAME is not set in .env}"
: "${DB_TEST_NAME:?DB_TEST_NAME is not set in .env}"
: "${DB_USER:?DB_USER is not set in .env}"
: "${DB_PASSWORD:?DB_PASSWORD is not set in .env}"
: "${DB_MIGRATOR_USER:?DB_MIGRATOR_USER is not set in .env}"
: "${DB_MIGRATOR_PASSWORD:?DB_MIGRATOR_PASSWORD is not set in .env}"

mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS \`${DB_TEST_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS '${DB_MIGRATOR_USER}'@'%' IDENTIFIED BY '${DB_MIGRATOR_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_MIGRATOR_USER}'@'%' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON \`${DB_TEST_NAME}\`.* TO '${DB_MIGRATOR_USER}'@'%' WITH GRANT OPTION;

CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT SELECT ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';
GRANT SELECT ON \`${DB_TEST_NAME}\`.* TO '${DB_USER}'@'%';

FLUSH PRIVILEGES;
SQL

echo "covenant init: created ${DB_NAME}, ${DB_TEST_NAME}, ${DB_MIGRATOR_USER} and ${DB_USER}"
