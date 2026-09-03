FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg (node was only needed to build the frontend
# in-image; the widget's dist/ is now built locally and shipped — that
# keeps image builds fast and away from npm-network flakiness)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (cached layer — reinstalled only when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + the PREBUILT frontend bundle (office-floor-widget/dist).
# Build it locally first: cd office-floor-widget && npm install && npm run build
COPY . .

# Expose AgentOS port
EXPOSE 8000

CMD ["python", "-m", "app.main"]
