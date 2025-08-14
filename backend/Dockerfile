# syntax=docker/dockerfile:1

# Use x86_64 to ensure widely available wheels (esp. PyTorch, FAISS) on Apple Silicon hosts
FROM --platform=$BUILDPLATFORM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps kept minimal to avoid triggering source builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first to leverage Docker layer cache
WORKDIR /app
# Build args to toggle heavy ML deps
ARG INCLUDE_ML=false
COPY requirements.txt requirements-core.txt requirements-ml.txt /app/
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && if [ "$INCLUDE_ML" = "true" ]; then pip install --no-cache-dir -r /app/requirements-ml.txt; fi

# Copy app source (will be overridden by bind mount in compose for dev)
COPY . /app

# Default command; compose may override
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
