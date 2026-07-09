# Tradebase Ingestion Service Dockerfile
# Multi-stage build for smaller production image

# =====================================================
# Stage 1: Builder
# =====================================================
FROM python:3.11-slim AS builder

# Set build arguments
ARG BUILD_DATE
ARG VERSION=1.0.0

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml ./

# Install dependencies to a temporary location
RUN pip install --no-cache-dir --prefix="/install" -e . && \
    rm -rf /root/.cache/pip

# =====================================================
# Stage 2: Runtime
# =====================================================
FROM python:3.11-slim

# Set labels
LABEL maintainer="Tradebase Team"
LABEL version="${VERSION}"
LABEL description="Tradebase Ingestion Service - Data ingestion from YFinance"
LABEL build-date="${BUILD_DATE}"
ENV PIP_ROOT_USER_ACTION=ignore
# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    INGESTION_PROVIDER=yfinance \
    INGESTION_INTERVAL=1m \
    INGESTION_SYMBOLS=EURUSD,GBPUSD,USDJPY

# Create non-root user
RUN groupadd -r tradebase && useradd -r -g tradebase tradebase

# Install runtime dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY services/ /app/services/
COPY libs/ /app/libs/
COPY config/ /app/config/

# Create necessary directories
RUN mkdir -p /app/logs /app/data && \
    chown -R tradebase:tradebase /app

# Switch to non-root user
USER tradebase

# Health check - verify process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Set entrypoint
ENTRYPOINT ["python", "-m", "services.ingestion.main"]

# Default command (can be overridden)
CMD []
