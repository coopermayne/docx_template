FROM python:3.11-slim

# Install system dependencies
# - libmagic1: required for python-magic (file type detection)
# - build-essential: for any packages needing compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories (will be overridden by volume mounts in production)
RUN mkdir -p /app/data/sessions /app/data/uploads

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
