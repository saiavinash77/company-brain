#!/usr/bin/env bash
# Migrates local docker Postgres (company-brain-db container) → Cloud SQL.
# Uses gcloud sql import with a dump taken from the local instance through
# the Cloud SQL Auth Proxy path (streamed via gs://) — no public IP exposed.
#
# What moves: schema ai.* (agno_sessions, agno_runs) + company_brain_knowledge
# (pgvector embeddings) — i.e. your team's memory and saved conversations.

set -euo pipefail
PROJECT="${PROJECT:-company-brain-456712}"
REGION="${REGION:-asia-south1}"
DB_INSTANCE="company-brain-db"
BUCKET="gs://${PROJECT}-cb-migrate"
LOCAL_CONTAINER="company-brain-db"

say() { printf '\n==> %s\n' "$*"; }

say "dumping local Postgres"
DUMP=/tmp/cb-migrate-$(date +%s).sql
docker exec "$LOCAL_CONTAINER" pg_dump -U scout -d companybrain \
  --no-owner --no-privileges > "$DUMP"
echo "dump: $(wc -c < "$DUMP") bytes"

say "uploading to $BUCKET (created if needed)"
gsutil mb -p "$PROJECT" "$BUCKET" >/dev/null 2>&1 || true
gsutil cp "$DUMP" "$BUCKET/import.sql"

say "importing into Cloud SQL (this can take a few minutes)"
gcloud sql import sql "$DB_INSTANCE" "$BUCKET/import.sql" \
  --database=companybrain --project="$PROJECT" --quiet \
  || { echo "import failed (maybe non-empty DB) — check gcloud sql operations list"; exit 1; }

say "cleaning up"
gsutil rm "$BUCKET/import.sql"
rm -f "$DUMP"
echo "migration done"
