#!/usr/bin/env bash
# Company Brain → GCP one-shot deploy.
#
# Prereqs (checked before anything runs):
#   - gcloud authenticated + billing ACTIVE on $PROJECT (console step)
#   - this repo directory as cwd
#
# What it does, in order:
#   1. enable APIs
#   2. create Cloud SQL Postgres 16 + pgvector (password in Secret Manager)
#   3. create Artifact Registry repo + build image via Cloud Build
#   4. create secrets (Groq/Gemini/Twilio keys, passcode, DB URL)
#   5. deploy to Cloud Run (VPC connection to Cloud SQL private IP)
#   6. migrate local data (optional, MIGRATE_DATA=1)
#   7. print the live URL + smoke-check /health
#
# Idempotent: every step checks for existing resources first, so re-running
# after a failure is safe and cheap.

set -euo pipefail

# ---- configuration -------------------------------------------------------
PROJECT="${PROJECT:-company-brain-456712}"
REGION="${REGION:-asia-south1}"          # Mumbai — closest to you
APP_NAME="company-brain"
DB_INSTANCE="company-brain-db"
DB_VERSION="POSTGRES_16"
DB_TIER="db-f1-d34ec1f4" # Skip — see below, gcloud handles tier via --tier
DB_TIER_REAL="db-g1-small"               # ~$9/mo, plenty for this app
AR_REPO="company-brain"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${APP_NAME}:latest"
CONN_NAME=""                             # filled after SQL creation

BILLING_WARN=1
MIGRATE_DATA="${MIGRATE_DATA:-1}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mFATAL: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 0. preflight --------------------------------------------------------
say "Preflight: project + billing"
gcloud config set project "$PROJECT" >/dev/null

BILLING=$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null || echo False)
if [[ "$BILLING" != "True" ]]; then
  cat <<'EOF'

Billing is NOT active on this project. Open:
  https://console.cloud.google.com/billing/linkedaccount?project=company-brain-456712
and link an ACTIVE billing account (reactivate the existing one or create
a new one — new accounts get $300 free credit). Then re-run this script.

EOF
  exit 1
fi

command -v gcloud >/dev/null || die "gcloud CLI not found"
[[ -f .env ]] || die ".env missing — copy .env.example and fill your keys"

# ---- 1. APIs -------------------------------------------------------------
say "Enabling APIs (first run takes ~2 min)"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com \
  --project="$PROJECT" --quiet

# ---- 2. Cloud SQL --------------------------------------------------------
say "Cloud SQL: Postgres 16 + pgvector ($DB_INSTANCE)"
if gcloud sql instances describe "$DB_INSTANCE" --project="$PROJECT" >/dev/null 2>&1; then
  echo "instance exists — reusing"
else
  # DB password: generate a strong one and store it in Secret Manager
  if gcloud secrets describe cb-db-password --project="$PROJECT" >/dev/null 2>&1; then
    DB_PASSWORD=$(gcloud secrets versions access latest --secret=cb-db-password --project="$PROJECT")
  else
    DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
    printf '%s' "$DB_PASSWORD" | gcloud secrets create cb-db-password \
      --data-file=- --project="$PROJECT" >/dev/null
  fi

  gcloud sql instances create "$DB_INSTANCE" \
    --database-version="$DB_VERSION" \
    --tier="$DB_TIER_REAL" \
    --region="$REGION" \
    --project="$PROJECT" \
    --storage-auto-increase \
    --backup-start-time=03:00 \
    --enable-point-in-time-recovery \
    --no-assign-public-ip \
    --network=projects/"$PROJECT"/global/networks/default \
    --quiet
  # ^ private IP only, on the default network; Cloud Run reaches it through
  #   the VPC connector created in step 5.

  gcloud sql databases create companybrain \
    --instance="$DB_INSTANCE" --project="$PROJECT" >/dev/null
  gcloud sql users create scout \
    --instance="$DB_INSTANCE" --project="$PROJECT" \
    --password="$DB_PASSWORD" >/dev/null || true

  # pgvector extension + agno schema pieces the app expects
  gcloud sql connect "$DB_INSTANCE" --project="$PROJECT" --quiet <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
SQL
fi

DB_PASSWORD=$(gcloud secrets versions access latest --secret=cb-db-password --project="$PROJECT")
CONN_NAME=$(gcloud sql instances describe "$DB_INSTANCE" --project="$PROJECT" --format='value(connectionName)')
DB_HOST=$(gcloud sql instances describe "$DB_INSTANCE" --project="$PROJECT" --format='value(ipAddresses[0].ipAddress)')
DATABASE_URL="postgresql+psycopg://scout:${DB_PASSWORD}@${DB_HOST}:5432/companybrain"
printf '%s' "$DATABASE_URL" | gcloud secrets create cb-database-url \
  --data-file=- --project="$PROJECT" >/dev/null 2>&1 \
  || printf '%s' "$DATABASE_URL" | gcloud secrets versions add cb-database-url --data-file=- --project="$PROJECT"

# ---- 3. image build ------------------------------------------------------
say "Artifact Registry + Cloud Build (no local Docker involved)"
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker --location="$REGION" --project="$PROJECT" >/dev/null 2>&1 \
  || echo "repo exists — reusing"

gcloud builds submit . \
  --config=deploy/cloudbuild.yaml \
  --project="$PROJECT" \
  --region="$REGION" \
  --substitutions=_IMAGE="${IMAGE}" \
  --quiet

# ---- 4. app secrets ------------------------------------------------------
say "Secret Manager: app keys + passcode"
make_secret() { # name, env-var-from-.env
  local name="$1" envvar="$2"
  local val
  val=$(grep -E "^${envvar}=" .env | head -1 | cut -d= -f2-)
  [[ -n "$val" ]] || { echo "skip $name ($envvar not set in .env)"; return; }
  if gcloud secrets describe "$name" --project="$PROJECT" >/dev/null 2>&1; then
    printf '%s' "$val" | gcloud secrets versions add "$name" --data-file=- --project="$PROJECT"
  else
    printf '%s' "$val" | gcloud secrets create "$name" --data-file=- --project="$PROJECT" >/dev/null
  fi
  echo "secret $name ok"
}
make_secret cb-groq-api-key     GROQ_API_KEY
make_secret cb-google-api-key   GOOGLE_API_KEY
make_secret cb-serper-api-key   SERPER_API_KEY
make_secret cb-twilio-sid       TWILIO_ACCOUNT_SID
make_secret cb-twilio-token     TWILIO_AUTH_TOKEN
make_secret cb-twilio-phone     TWILIO_PHONE_NUMBER
make_secret cb-owner-number    OWNER_NUMBER
# Auth0 (optional — backend accepts Auth0 tokens in addition to the passcode)
make_secret cb-auth0-domain     AUTH0_DOMAIN
make_secret cb-auth0-audience   AUTH0_AUDIENCE
make_secret cb-auth0-client-id  AUTH0_CLIENT_ID
make_secret cb-auth0-client-secret AUTH0_CLIENT_SECRET

# Passcode gate: reuse an existing secret or generate one and TELL the user
if gcloud secrets describe cb-app-passcode --project="$PROJECT" >/dev/null 2>&1; then
  echo "passcode secret exists"
else
  PASSCODE="${APP_PASSCODE:-$(openssl rand -base64 12 | tr -d '/+=' | head -c 10)}"
  printf '%s' "$PASSCODE" | gcloud secrets create cb-app-passcode --data-file=- --project="$PROJECT" >/dev/null
  echo
  echo "  ┌─────────────────────────────────────────────"
  echo "  │ APP PASSCODE: $PASSCODE"
  echo "  │ (also stored in secret cb-app-passcode)"
  echo "  └─────────────────────────────────────────────"
  echo
fi

# ---- 5. Cloud Run --------------------------------------------------------
say "Cloud Run deploy"
# VPC connector so Cloud Run reaches Cloud SQL's private IP
if ! gcloud compute networks vpc-access connectors describe cb-connector --region="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud compute networks vpc-access connectors create cb-connector \
    --region="$REGION" --range=10.8.0.0/28 \
    --network=default --project="$PROJECT" --quiet
fi

# Assemble the secrets list dynamically: base secrets always, Serper/Auth0
# only when their Secret Manager entries exist (they're optional).
SECRET_LIST="GROQ_API_KEY=cb-groq-api-key:latest,GOOGLE_API_KEY=cb-google-api-key:latest,TWILIO_ACCOUNT_SID=cb-twilio-sid:latest,TWILIO_AUTH_TOKEN=cb-twilio-token:latest,TWILIO_PHONE_NUMBER=cb-twilio-phone:latest,OWNER_NUMBER=cb-owner-number:latest,APP_PASSCODE=cb-app-passcode:latest,DATABASE_URL=cb-database-url:latest"
for opt in "cb-serper-api-key:SERPER_API_KEY" "cb-auth0-domain:AUTH0_DOMAIN" "cb-auth0-audience:AUTH0_AUDIENCE" "cb-auth0-client-id:AUTH0_CLIENT_ID" "cb-auth0-client-secret:AUTH0_CLIENT_SECRET"; do
  name="${opt%%:*}"; envvar="${opt##*:}"
  if gcloud secrets describe "$name" --project="$PROJECT" >/dev/null 2>&1; then
    SECRET_LIST="${SECRET_LIST},${envvar}=${name}:latest"
  fi
done

gcloud run deploy "$APP_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT" \
  --port=8000 \
  --min-instances=1 \
  --max-instances=3 \
  --cpu=1 --memory=1Gi \
  --timeout=300 \
  --vpc-connector=cb-connector \
  --set-env-vars=AGENTOS_HOST=0.0.0.0,AGENTOS_PORT=8000,GATE_SECURE_COOKIE=1 \
  --set-secrets="$SECRET_LIST" \
  --allow-unauthenticated \
  --quiet

URL=$(gcloud run services describe "$APP_NAME" --region="$REGION" --project="$PROJECT" --format='value(status.url)')

# ---- 6. data migration (optional) ----------------------------------------
if [[ "$MIGRATE_DATA" == "1" ]] && command -v docker >/dev/null && docker ps >/dev/null 2>&1; then
  say "Migrating local data → Cloud SQL (sessions, runs, knowledge)"
  bash deploy/migrate-data.sh || echo "migration skipped/failed — app still works, history starts fresh"
fi

# ---- 7. smoke check ------------------------------------------------------
say "Smoke check"
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL/health" || true)
  [[ "$code" == "200" ]] && break
  sleep 5
done
if [[ "$code" == "200" ]]; then
  cat <<EOF

  ┌────────────────────────────────────────────────────────────┐
  │  DEPLOYED ✓                                                │
  │                                                            │
  │  URL:        $URL                      │
  │  Health:     ok                                            │
  │  Database:   Cloud SQL ($DB_INSTANCE, private IP)          │
  │  Auth:       passcode gate (secret: cb-app-passcode)       │
  │                                                            │
  │  Twilio WhatsApp webhook → update the URL in the Twilio    │
  │  console to: $URL/webhook/whatsapp    │
  └────────────────────────────────────────────────────────────┘
EOF
else
  echo "health check failed — inspect: gcloud run services logs read $APP_NAME --region $REGION"
  exit 1
fi
