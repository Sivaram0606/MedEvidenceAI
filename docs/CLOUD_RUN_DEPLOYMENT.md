# Google Cloud Run Deployment Guide (`MedEvidenceAI`)

This guide provides step-by-step instructions to containerize and deploy **MedEvidenceAI** to **Google Cloud Run**, with live **Vertex AI (`gemini-3.8-flash`)** synthesis and secure browser access via **Identity-Aware Proxy (IAP)** (or public unauthenticated ingress where organization policies permit).

---

## Live Cloud Run Service Summary

| Setting | Value |
| :--- | :--- |
| **Service Name** | `medevidence-ai` |
| **GCP Project ID** | `my-project-ssi-364811` |
| **Region** | `us-central1` |
| **Service URL** | `https://medevidence-ai-1018040469825.us-central1.run.app` |
| **Runtime Service Account** | `medevidence-ai-sa@my-project-ssi-364811.iam.gserviceaccount.com` |
| **LLM Reasoning Backend** | Vertex AI (`gemini-3.8-flash`, `GOOGLE_CLOUD_LOCATION=global`) |
| **Browser Authentication** | Cloud Run Direct IAP (`--iap`) with Google SSO |

---

## Option A: Automated 1-Command Deployment

From the repository root, run [`deploy_cloudrun.sh`](../deploy_cloudrun.sh):

```bash
export PROJECT_ID="my-project-ssi-364811"
export REGION="us-central1"

# Default: Enterprise IAP-protected browser login (recommended for GCP Org projects)
./deploy_cloudrun.sh

# Optional: Public unauthenticated deployment (only if your GCP Org allows 'allUsers')
# AUTH_MODE=public ./deploy_cloudrun.sh
```

---

## Option B: Step-by-Step Manual Deployment

### Step 1: Authenticate & Set Your GCP Project

```bash
gcloud auth login
export PROJECT_ID="my-project-ssi-364811"
export REGION="us-central1"
export SERVICE_NAME="medevidence-ai"
export SA_NAME="medevidence-ai-sa"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}"
```

### Step 2: Enable Required Google Cloud APIs

Enable Cloud Run, Cloud Build, Artifact Registry, Vertex AI (`aiplatform`), and IAP:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  iap.googleapis.com \
  --project="${PROJECT_ID}"
```

### Step 3: Create a Dedicated Least-Privilege Service Account

Grant the Cloud Run runtime service account only `roles/aiplatform.user` (for Vertex AI Gemini Flash 3.8 synthesis) and `roles/logging.logWriter`:

```bash
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="MedEvidenceAI Cloud Run Service Account" \
  --project="${PROJECT_ID}"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user" \
  --condition=None

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/logging.logWriter" \
  --condition=None
```

### Step 4: Build & Deploy from Source to Cloud Run

Cloud Build uses [`Dockerfile`](../Dockerfile), [`.dockerignore`](../.dockerignore), and [`.gcloudignore`](../.gcloudignore) to package only runtime code (`backend/`, `static/`, `requirements.txt`) on `python:3.14-slim` as a non-root user listening on `$PORT` (`8080`):

```bash
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --iap \
  --no-allow-unauthenticated \
  --session-affinity \
  --cpu-boost \
  --cpu=2 \
  --memory=2Gi \
  --concurrency=20 \
  --max-instances=5 \
  --timeout=300 \
  --port=8080 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=gemini-3.8-flash"
```

> [!TIP]
> **Why `--session-affinity` and `--timeout=300`?**
> - `--session-affinity` routes requests from the same clinician browser session to the same Cloud Run instance so custom journal whitelist edits (`/api/journals`) stay consistent in memory.
> - `--timeout=300` accommodates parallel live queries across NCBI PubMed, Europe PMC, OpenAlex, and ClinicalTrials.gov v2 followed by structured Gemini synthesis.
> - If your GCP project does **not** restrict `allUsers` via `constraints/iam.allowedPolicyMemberDomains` and you want public unauthenticated access instead of IAP, replace `--iap --no-allow-unauthenticated` with `--allow-unauthenticated --no-iap`.

### Step 5: Grant Browser Access via Identity-Aware Proxy (IAP)

Grant authorized clinicians or team members (`user:EMAIL` or `group:GROUP_EMAIL`) access to open the Cloud Run URL in their browser:

```bash
export USER_EMAIL="$(gcloud config get-value account)"

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="user:${USER_EMAIL}" \
  --role="roles/run.invoker"

gcloud iap web add-iam-policy-binding \
  --resource-type=cloud-run \
  --service="${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="user:${USER_EMAIL}" \
  --role="roles/iap.httpsResourceAccessor"
```

---

## Optional Environment Variables

You can update runtime environment variables at any time without rebuilding the container:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GOOGLE_CLOUD_PROJECT` | `my-project-ssi-364811` | GCP Project ID for Vertex AI ADC authentication |
| `GOOGLE_CLOUD_LOCATION` | `global` | Vertex AI endpoint location |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model ID used by Agents 3 & 4 |
| `GEMINI_API_KEY` | *(Unset)* | Optional AI Studio API key (if set, overrides Vertex AI ADC) |
| `NCBI_API_KEY` | *(Unset)* | Optional NCBI E-Utilities API key to raise PubMed rate limits from 3 req/s to 10 req/s |
| `FHIR_ALLOWED_HOSTS` | *(Default public sandboxes)* | Comma-separated additional allowed hostnames for `/api/parse-fhir` URL fetching |

Example update command:

```bash
gcloud run services update "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --update-env-vars="NCBI_API_KEY=your_ncbi_key"
```

---

## Step 6: Verification & Local Proxy Testing

### 1. Open Directly in Browser (via IAP Google Sign-In)
Navigate to your deployed Cloud Run URL (e.g., `https://medevidence-ai-1018040469825.us-central1.run.app`) while signed in with an authorized Google account.

### 2. Local Authenticated Proxy (for CLI / `curl` testing behind IAP)
Cloud Run's built-in proxy authenticates automatically using your local `gcloud` credentials:

```bash
gcloud run services proxy "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --port=8085
```

Then in another terminal (or at `http://127.0.0.1:8085`):

```bash
curl -s http://127.0.0.1:8085/api/health | python3 -m json.tool
```

### 3. Inspect Cloud Run Logs

```bash
gcloud run services logs read "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --limit=50
```
