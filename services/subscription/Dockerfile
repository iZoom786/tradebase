FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY libs/ /app/libs/
COPY services/subscription/ /app/services/subscription/

# Create logs directory
RUN mkdir -p /var/log/subscription

# Set Python path
ENV PIP_ROOT_USER_ACTION=ignore
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8002/health')" || exit 1

# Run the application
CMD ["uvicorn", "services.subscription.main:app", "--host", "0.0.0.0", "--port", "8002"]
