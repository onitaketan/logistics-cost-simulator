#!/bin/sh
# Container entrypoint for the API and worker images.
#
# Responsibilities (idempotent, safe to run on every boot):
#   1. Wait for PostgreSQL to accept connections.
#   2. When RUN_MIGRATIONS=true (the api service): apply every migrations/*.sql
#      exactly once, tracked in a schema_migrations ledger table, then run the
#      idempotent seed. The worker service sets RUN_MIGRATIONS=false and only
#      waits for the DB (the api has already migrated by the time work arrives).
#   3. exec the given command (uvicorn / celery).
#
# Migrations are applied with psql so PL/pgSQL bodies and $$-quoting in
# 0001_init.sql are handled verbatim. DATABASE_URL is the SQLAlchemy form
# (postgresql+psycopg://…); strip the +driver suffix for libpq/psql.
set -eu

PSQL_URL=$(printf '%s' "${DATABASE_URL:-}" | sed -E 's/\+psycopg2?//')

if [ -z "$PSQL_URL" ]; then
  echo "[entrypoint] DATABASE_URL is not set" >&2
  exit 1
fi

echo "[entrypoint] waiting for database…"
i=0
until pg_isready -d "$PSQL_URL" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "[entrypoint] database not ready after 60s" >&2
    exit 1
  fi
  sleep 1
done
echo "[entrypoint] database is ready."

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] ensuring migration ledger…"
  psql "$PSQL_URL" -v ON_ERROR_STOP=1 -q -c \
    "CREATE TABLE IF NOT EXISTS schema_migrations (filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());"

  for f in $(ls migrations/*.sql | sort); do
    name=$(basename "$f")
    applied=$(psql "$PSQL_URL" -tAc "SELECT 1 FROM schema_migrations WHERE filename='$name'")
    if [ "$applied" = "1" ]; then
      echo "[entrypoint] skip $name (already applied)"
    else
      echo "[entrypoint] apply $name"
      psql "$PSQL_URL" -v ON_ERROR_STOP=1 -q -f "$f"
      psql "$PSQL_URL" -q -c "INSERT INTO schema_migrations (filename) VALUES ('$name')"
    fi
  done

  echo "[entrypoint] seeding (idempotent)…"
  python scripts/seed.py || echo "[entrypoint] seed reported an issue (non-fatal); continuing."
fi

echo "[entrypoint] starting: $*"
exec "$@"
