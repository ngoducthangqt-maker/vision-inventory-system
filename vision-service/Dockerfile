# ---- Build stage ----
# Uses a full Python image so torch/ultralytics build wheels cleanly.
FROM python:3.11-slim AS builder

# Build deps for opencv / torch / numpy
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc g++ build-essential \
        libgl1 libglib2.0-0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

# Runtime libs: ffmpeg for RTSP/video decoding, libgl/glib for OpenCV.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app app

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

COPY --chown=app:app . .

USER app

EXPOSE 8001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3); sys.exit(0)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
