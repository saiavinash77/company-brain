#!/usr/bin/env bash
# Company Brain → FAST app-only redeploy (~5-8 min).
#
# Use this after the FIRST full deploy (deploy/deploy.sh) has created
# Cloud SQL / VPC connector / secrets. It pushes new app+frontend code only:
#
#   1. build the widget locally (fast, ~13s)
#   2. Cloud Build the image (Python layers cached unless requirements.txt changed)
#   3. update the existing Cloud Run service (same secrets, same DB)
#   4. smoke-check /health
#
# Typical flow after you change code:
#   git commit && bash deploy/redeploy.sh
#
# No local Docker involved — the crashy Docker Desktop never blocks you.

set -euo pipefail

PROJECT="${PROJECT:-company-brain-live}"
REGION="${REGION:-asia-south1}"
APP_NAME="company-brain"
AR_REPO="company-brain"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${APP_NAME}:latest"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mFATAL: %s\033[0m\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud CLI not found"
gcloud config set project "$PROJECT" >/dev/null

# ---- 1. frontend -----------------------------------------------------------
say "Building office-floor-widget (local)"
( cd office-floor-widget && npm run build ) \
  || die "widget build failed — fix the JSX/build error first"

[[ -f office-floor-widget/dist/index.html ]] || die "dist/ missing after build"

# ---- 2. image --------------------------------------------------------------
say "Cloud Build: image + push (Python layers cached)"
gcloud builds submit . \
  --config=deploy/cloudbuild.yaml \
  --project="$PROJECT" \
  --region="$REGION" \
  --substitutions=_IMAGE="${IMAGE}" \
  --quiet

# ---- 3. Cloud Run update ----------------------------------------------------
say "Cloud Run: updating service (existing secrets/DB untouched)"
gcloud run deploy "$APP_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT" \
  --quiet

URL=$(gcloud run services describe "$APP_NAME" --region="$REGION" --project="$PROJECT" --format='value(status.url)')

# ---- 4. smoke ---------------------------------------------------------------
say "Smoke check"
sleep 5
for i in $(seq 1 12); do
  CODE=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "${URL}/health" || echo 000)
  [[ "$CODE" == "200" ]] && break
  echo "  waiting for boot (${CODE})…"; sleep 10
done
[[ "$CODE" == "200" ]] || die "service did not come up healthy — check: gcloud run services logs read $APP_NAME --region=$REGION --limit=50"

echo
echo "  ┌───────────────────────────────────────────────────"
echo "  │ LIVE: $URL"
echo "  └───────────────────────────────────────────────────"
