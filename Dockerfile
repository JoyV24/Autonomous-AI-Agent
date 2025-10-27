FROM python:3.11-slim

# Install system build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential gcc g++ git curl ca-certificates \
      python3-dev libffi-dev libssl-dev libpq-dev libopenblas-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt

RUN pip install --upgrade pip setuptools wheel

# Try legacy resolver first
RUN pip install --no-cache-dir --use-deprecated=legacy-resolver -r /app/requirements.txt

# Install spacy model separately if needed
# RUN python -m spacy download en_core_web_sm

COPY . /app

EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]