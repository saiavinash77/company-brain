FROM python:3.12-slim

WORKDIR /app


# psycopg[binary] bundles the PostgreSQL client libraries, so no OS package
# installation is required for the application image.
# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose AgentOS port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "app.main"]
