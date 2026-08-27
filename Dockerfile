FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg + node build
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build the office-floor-widget frontend
COPY office-floor-widget/ ./office-floor-widget/
RUN cd office-floor-widget && npm install && npm run build

# Copy application code (after build so dist is present; .dockerignore excludes secrets)
COPY . .

# Expose AgentOS port
EXPOSE 8000

CMD ["python", "-m", "app.main"]
