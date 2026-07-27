FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--workers", "4", "--threads", "2", "--worker-class", "gthread", "--bind", "0.0.0.0:5000", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
