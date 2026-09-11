FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for PostgreSQL, build tools, and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies directly into system environment
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Set up runtime directories and environment
RUN mkdir -p /app/uploads
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 10000

# Start FastAPI server using entrypoint script with explicit startup tracing
CMD ["python", "entrypoint.py"]

