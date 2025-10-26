# Dockerfile — place at repo root
FROM python:3.11-slim

# Install system build tools and libs needed to compile C extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential gcc g++ git curl ca-certificates \
      python3-dev libffi-dev libssl-dev libpq-dev libopenblas-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first to use Docker cache
COPY backend/requirements.txt /app/requirements.txt

# Upgrade pip and install PEP517 helpers
RUN pip install --upgrade pip setuptools wheel build cython

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

# Expose a port (Render / Railway provide PORT)
EXPOSE 8080

# Start command (reads PORT env)
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
