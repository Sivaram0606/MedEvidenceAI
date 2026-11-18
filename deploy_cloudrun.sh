#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# MedEvidenceAI • Automated Google Cloud Run Deployment Script
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-medevidence-ai}"
SA_NAME="${SA_NAME:-medevidence-ai-sa}"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
# AUTH_MODE options: "iap" (recommended for enterprise/organization projects) or "public"
AUTH_MODE="${AUTH_MODE:-iap}"
ACTIVE_USER="${ACTIVE_USER:-$(gcloud config get-value account 2>/dev/null)}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "ERROR: PROJECT_ID is not set. Run 'gcloud config set project YOUR_PROJECT_ID' or export PROJECT_ID."
  exit 1
fi

echo "==> Deploying ${SERVICE_NAME} to project '${PROJECT_ID}' (${REGION}) [AUTH_MODE=${AUTH_MODE}]"

echo "==> [1/4] Enabling required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  iap.googleapis.com \
  --project="${PROJECT_ID}"

echo "==> [2/4] Ensuring dedicated least-privilege Service Account (${SA_EMAIL})..."
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="MedEvidenceAI Cloud Run Service Account" \
    --project="${PROJECT_ID}"
fi

for ROLE in roles/aiplatform.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet >/dev/null
done

AUTH_FLAGS=(--no-allow-unauthenticated --iap)
if [[ "${AUTH_MODE}" == "public" ]]; then
  AUTH_FLAGS=(--allow-unauthenticated --no-iap)
fi

echo "==> [3/4] Building container image via Cloud Build and deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  "${AUTH_FLAGS[@]}" \
  --session-affinity \
  --cpu-boost \
  --cpu=2 \
  --memory=2Gi \
  --concurrency=20 \
  --max-instances=5 \
  --timeout=300 \
  --port=8080 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION},GEMINI_MODEL=${GEMINI_MODEL}" \
  --quiet

echo "==> [4/4] Configuring access permissions..."
if [[ "${AUTH_MODE}" == "iap" && -n "${ACTIVE_USER}" ]]; then
  gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --member="user:${ACTIVE_USER}" \
    --role="roles/run.invoker" \
    --quiet >/dev/null

  gcloud iap web add-iam-policy-binding \
    --resource-type=cloud-run \
    --service="${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --member="user:${ACTIVE_USER}" \
    --role="roles/iap.httpsResourceAccessor" \
    --quiet >/dev/null
fi

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')"
echo ""
echo "=============================================================================="
echo " Deployment Complete!"
echo " Service URL : ${SERVICE_URL}"
echo " Health Check: ${SERVICE_URL}/api/health"
echo "=============================================================================="
