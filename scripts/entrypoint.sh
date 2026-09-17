#!/bin/sh
set -eu

export OPOTEST_DB_PATH="${OPOTEST_DB_PATH:-/data/app.db}"
export OPOTEST_ADMIN_USERNAME="opotest_bootstrap"
export OPOTEST_ADMIN_PASSWORD="DemoBootstrap-Only-2026!"
export OPOTEST_ADMIN_DISPLAY_NAME="OpoTest Bootstrap"

mkdir -p "$(dirname "$OPOTEST_DB_PATH")"

yoyo --no-config-file --batch apply \
  --database "sqlite:///$OPOTEST_DB_PATH" \
  migrations

python /app/seed.py --db "$OPOTEST_DB_PATH"

exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips='*'
