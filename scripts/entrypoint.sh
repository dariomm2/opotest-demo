#!/bin/sh
set -eu

export OPTEST_DB_PATH="${OPTEST_DB_PATH:-/data/app.db}"
export OPTEST_ADMIN_USERNAME="optest_bootstrap"
export OPTEST_ADMIN_PASSWORD="DemoBootstrap-Only-2026!"
export OPTEST_ADMIN_DISPLAY_NAME="OpoTest Bootstrap"

mkdir -p "$(dirname "$OPTEST_DB_PATH")"

yoyo --no-config-file --batch apply \
  --database "sqlite:///$OPTEST_DB_PATH" \
  migrations

python /app/seed.py --db "$OPTEST_DB_PATH"

exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips='*'
