# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install system deps (if any)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Copy requirement files first for layer caching
COPY ../requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app (depuis la racine du projet)
COPY ../ ./

# Create a non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 28080
# Gunicorn app entry (module:function)
# If your repo structure is different, adjust webapp.app:app accordingly.
CMD ["gunicorn", "--bind", "0.0.0.0:28080", "--workers", "3", "webapp.app:app"]
