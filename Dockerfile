FROM python:3.11-slim

# System dependencies for WeasyPrint PDF generation and ML
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install server dependencies not in requirements.txt
RUN pip install --no-cache-dir \
    fastapi>=0.104.0 \
    uvicorn>=0.24.0 \
    sse-starlette>=1.8.0 \
    watchfiles>=0.21.0

# Copy application code
COPY src/ src/
COPY scripts/ scripts/
COPY config/ config/
COPY architecture.md .
COPY ground_rules.md .

# Create necessary directories
RUN mkdir -p outputs/polaris_graph logs state data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default port
EXPOSE 8000

# Entry point
COPY scripts/docker_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
