# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install only runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root user with a real home directory
RUN addgroup --system --gid 1001 inquira && \
    adduser --system --uid 1001 --ingroup inquira --home /home/inquira inquira

ENV HOME=/home/inquira
ENV HF_HOME=/home/inquira/.cache

# Copy application source
COPY . .

# Create directories owned by app user
RUN mkdir -p /app/uploads /home/inquira/.cache && \
    chown -R inquira:inquira /app /home/inquira

USER inquira

EXPOSE 8000

# Use gunicorn with dynamic port and memory-safe concurrency for cloud hosts (e.g. Render 512MB)
CMD ["sh", "-c", "gunicorn app.main:app -w ${WEB_CONCURRENCY:-1} -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8000} --access-logfile - --error-logfile -"]

