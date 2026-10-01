# Block model builder: the FastAPI engine and the built web app, served on one port.
#
#   docker build --build-arg BUILD_HASH=$(git rev-parse --short HEAD) -t block-model-builder .
#   docker run -p 8000:8000 -v bm-data:/data \
#     -e BM_AUTH_USER=team -e BM_AUTH_PASSWORD=change-me block-model-builder
#
# Behind a proxy that re-signs TLS, pass its CA bundle as a build secret:
#   --secret id=ca,src=/path/to/ca-bundle.crt
# It's used only by the download steps and never lands in the image.

# ---------------------------------------------------------------- web build
FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; fi; \
    npm ci --no-audit --no-fund
COPY styles /app/styles
COPY web ./
# The footer's build hash: BUILD_HASH if given, else the commit a host provides as a build arg
# (Render passes service env vars, including RENDER_GIT_COMMIT; Railway has RAILWAY_GIT_COMMIT_SHA).
# vite.config.ts picks the first one set and shortens it; "unknown" if none.
ARG BUILD_HASH RENDER_GIT_COMMIT RAILWAY_GIT_COMMIT_SHA
RUN npm run build

# ---------------------------------------------------------------- python environment
FROM python:3.12-slim AS py
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# The repo layout is kept: the server finds models/examples relative to its own path.
COPY pyproject.toml uv.lock ./
COPY engine engine
COPY server server
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca SSL_CERT_FILE=/run/secrets/ca; fi; \
    pip install --no-cache-dir --disable-pip-version-check "uv==0.8.17" \
    && uv sync --frozen --no-dev

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=py /app /app
COPY models/examples models/examples
COPY --from=web /app/web/dist web/dist

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app \
    && mkdir -p /data/models /data/blocks && chown -R app:app /data
# No VOLUME line: Railway rejects Dockerfiles that have one. Mount /data with -v or the host's disk.
# No USER line: the entrypoint starts as root to take ownership of a root-owned disk, then runs
# the server as the app user.
ENV PATH=/app/.venv/bin:$PATH \
    BM_WEB_DIR=/app/web/dist BM_DATA_DIR=/data/models BM_BLOCKS_DIR=/data/blocks \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)"
# Many hosts set PORT; default 8000.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir server --host 0.0.0.0 --port ${PORT:-8000}"]
