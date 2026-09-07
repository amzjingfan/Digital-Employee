#!/bin/sh
set -eu

: "${CASDOOR_DB_PASSWORD:?CASDOOR_DB_PASSWORD is required}"
: "${STAFFDECK_MIGRATOR_PASSWORD:?STAFFDECK_MIGRATOR_PASSWORD is required}"
: "${STAFFDECK_RUNTIME_PASSWORD:?STAFFDECK_RUNTIME_PASSWORD is required}"
: "${STAFFDECK_WORKER_PASSWORD:?STAFFDECK_WORKER_PASSWORD is required}"

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=casdoor_password="$CASDOOR_DB_PASSWORD" \
  --set=migrator_password="$STAFFDECK_MIGRATOR_PASSWORD" \
  --set=runtime_password="$STAFFDECK_RUNTIME_PASSWORD" \
  --set=worker_password="$STAFFDECK_WORKER_PASSWORD" <<'EOSQL'
SELECT format(
  'CREATE ROLE casdoor LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
  :'casdoor_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'casdoor') \gexec

SELECT format(
  'CREATE ROLE staffdeck_migrator LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
  :'migrator_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'staffdeck_migrator') \gexec

SELECT format(
  'CREATE ROLE staffdeck_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
  :'runtime_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'staffdeck_runtime') \gexec

SELECT format(
  'CREATE ROLE staffdeck_worker LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
  :'worker_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'staffdeck_worker') \gexec

SELECT 'CREATE DATABASE casdoor OWNER casdoor'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'casdoor') \gexec

SELECT 'CREATE DATABASE staffdeck_app OWNER staffdeck_migrator'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'staffdeck_app') \gexec

REVOKE CONNECT ON DATABASE casdoor FROM PUBLIC;
GRANT CONNECT ON DATABASE casdoor TO casdoor;

REVOKE CONNECT ON DATABASE staffdeck_app FROM PUBLIC;
GRANT CONNECT ON DATABASE staffdeck_app TO staffdeck_migrator, staffdeck_runtime, staffdeck_worker;
EOSQL

