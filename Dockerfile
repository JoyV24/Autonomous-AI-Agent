# Dockerfile (place at repo root)
FROM python:3.11-slim

# Install system build tools & common libs for building Python C-extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential gcc g++ git curl ca-certificates \
      python3-dev libffi-dev libssl-dev libpq-dev libopenblas-dev && \
    rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy only the backend requirements first (cacheable layer)
COPY backend/requirements.txt /app/requirements.txt

# Upgrade pip and install build helpers (helps pyproject builds)
RUN pip install --upgrade pip setuptools wheel build cython

# Install Python dependencies from the backend/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the entire repo after installing deps
COPY . /app

# Expose the port Render will provide (default mapping)
EXPOSE 8080

# Start the FastAPI app
# NOTE: your main is at backend/app/main.py and should define `app = FastAPI()`
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
