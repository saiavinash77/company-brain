FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose AgentOS port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "app.main"]
