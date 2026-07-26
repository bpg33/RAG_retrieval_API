# Synology RAG Retrieval Platform - REST API container.
# Native Windows execution is also fully supported (see docs/deployment-windows.md).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package (dependencies resolved from pyproject.toml).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Provide the example schema mapping; mount the real one at runtime.
COPY config ./config

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

# Inside the container the service must listen on all interfaces; the port is
# published only to 127.0.0.1 on the host (see docker-compose.yml). This requires
# ALLOW_NON_LOCAL_BIND=true, set in the compose file.
ENV BIND_HOST=0.0.0.0 \
    BIND_PORT=8765

EXPOSE 8765

# Simple liveness check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/health/live').status==200 else 1)"

CMD ["python", "-m", "synology_rag.api"]
