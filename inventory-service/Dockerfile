# ---- Build stage ----
FROM python:3.12-slim AS builder

# Install build dependencies required by asyncpg / psycopg
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install dependencies into a prefix we can copy into the final image
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

# Runtime libs only (no compiler)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app app

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source
COPY --chown=app:app . .

# Create a non-root user and switch to it
USER app

# Expose the service port
EXPOSE 8000

# Default environment (can be overridden at runtime / docker-compose)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

# Healthcheck hits the /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3); sys.exit(0)" || exit 1

# Run with uvicorn. In production prefer gunicorn + uvicorn workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
