# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Unbuffered stdout so logs stream straight to `docker logs`
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Run as a non-root user
RUN useradd -r -u 1001 -m -d /app -s /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
