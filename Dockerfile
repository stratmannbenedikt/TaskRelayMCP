FROM node:24.8.0-alpine3.22 AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12.11-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" TASKRELAY_DATABASE_URL="sqlite:////data/workspace.db"
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.10
COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY migrations/ migrations/
COPY src/ src/
COPY --from=frontend /build/src/taskrelaymcp/static src/taskrelaymcp/static
RUN uv sync --frozen --no-dev && mkdir /data && chown -R 10001:10001 /app /data
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"]
CMD ["taskrelaymcp"]
