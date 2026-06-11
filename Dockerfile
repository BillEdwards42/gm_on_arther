# ==========================================
# Self-Hosted Build (Docker Compose)
# ==========================================
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed for asyncpg (PostgreSQL C bindings)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies
# We increase timeout to handle the large torch download
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --timeout 1000 -r requirements.txt

# Copy Application Code
COPY app ./app

# Create local storage directory
RUN mkdir -p /app/data/storage

# Create a non-root user (Security Best Practice)
RUN useradd -m -u 1000 runner
# Change ownership
RUN chown -R runner:runner /app
# Switch to non-root user
USER runner

ENV PORT=8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
