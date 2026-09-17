FROM alpine:3.22 AS source

RUN apk add --no-cache git python3
ARG OPOTEST_SOURCE_REF=16b1d5c077c356e49f91f915a175522817e3401f
ARG OPOTEST_SOURCE_REPO_A=bomba
ARG OPOTEST_SOURCE_REPO_B=vtest
RUN git clone --no-tags "https://github.com/dariomm2/${OPOTEST_SOURCE_REPO_A}${OPOTEST_SOURCE_REPO_B}.git" /src \
    && cd /src \
    && git checkout --detach "$OPOTEST_SOURCE_REF" \
    && rm -rf /src/.git

COPY scripts/patch.py /build/patch.py
COPY scripts/runtime.py /build/runtime.py
RUN python3 /build/patch.py /src /build/runtime.py --base-path /opotest

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPOTEST_DB_PATH=/data/app.db \
    OPOTEST_VERSION=v14 \
    OPOTEST_DEMO_MODE=1 \
    OPOTEST_BASE_PATH=/opotest \
    OPOTEST_DEMO_ROOT=/tmp/opotest-demo \
    OPOTEST_DEMO_ASSET_ROOT=/app/demo_attachments \
    OPOTEST_DEMO_TTL_SECONDS=21600

WORKDIR /app
COPY --from=source /src/pyproject.toml ./pyproject.toml
RUN python -m pip install --no-cache-dir --group runtime
COPY --from=source /src/src/backend ./backend
COPY --from=source /src/src/frontend ./frontend
COPY --from=source /src/migrations ./migrations
COPY scripts/seed.py ./seed.py
COPY scripts/entrypoint.sh ./entrypoint.sh
RUN mkdir -p /data /tmp/opotest-demo /app/demo_attachments && chmod +x /app/entrypoint.sh /app/seed.py

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import os, urllib.request; port=os.environ.get('PORT','8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
