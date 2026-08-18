#!/usr/bin/env bash
# ==============================================================================
#      FRONTIER PULSE - GCP SERVERLESS DEPLOYMENT SCRIPT (GEN 2)
# ==============================================================================
# This script automates the provisioning of GCP services, creation of GCS bucket,
# initialization of secrets in Secret Manager, setup of secure least-privilege
# custom service accounts (for both build, execution, and triggering), and 
# deployment of the Cloud Run Function + Cloud Scheduler trigger.
#
# Highly resilient: Uses automatic retry loops with exponential backoff
# to overcome transient GCP IAM eventual consistency / propagation delays.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh <GCP_PROJECT_ID>
# ==============================================================================

set -eo pipefail

# 1. Configuration & Argument Parsing
PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
    echo -e "\n[!] Error: Please provide your GCP Project ID."
    echo -e "Usage:\n  ./deploy.sh <GCP_PROJECT_ID> [REGION]\n"
    exit 1
fi

REGION="${2:-us-central1}"  # Default region with high availability for TTS, Vertex AI, and Gemini
FUNCTION_NAME="frontier-pulse-weekly"
BUCKET_NAME="frontier-pulse-data-${PROJECT_ID}"
SCHEDULER_JOB_NAME="frontier-pulse-trigger"

# Custom Service Account Names
RUNNER_SA="frontier-pulse-runner"
RUNNER_SA_EMAIL="${RUNNER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

INVOKER_SA="frontier-pulse-invoker"
INVOKER_SA_EMAIL="${INVOKER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "================================================================="
echo "  Deploying Frontier Pulse to GCP Project: ${PROJECT_ID}"
echo "  Region: ${REGION}"
echo "  Bucket: gs://${BUCKET_NAME}"
echo "  Custom Runner SA: ${RUNNER_SA_EMAIL}"
echo "  Custom Invoker SA: ${INVOKER_SA_EMAIL}"
echo "================================================================="

# Set active project
gcloud config set project "${PROJECT_ID}"

# Helper function to run commands with retries and exponential backoff
# Extremely important for overcoming GCP IAM eventual consistency / propagation delays
run_with_retry() {
    local max_attempts=5
    local attempt=1
    local delay=2

    until "$@"; do
        if (( attempt == max_attempts )); then
            echo "[!] Error: Action failed after $max_attempts attempts."
            return 1
        fi
        echo "[!] Action failed. This is usually due to GCP IAM propagation delays. Retrying in $delay seconds (Attempt $attempt/$max_attempts)..."
        sleep $delay
        ((attempt++))
        ((delay*=2))
    done
    return 0
}

# 2. Enable Required APIs
echo -e "\n[*] Step 1: Enabling required GCP Service APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudfunctions.googleapis.com \
    secretmanager.googleapis.com \
    texttospeech.googleapis.com \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com \
    logging.googleapis.com \
    iam.googleapis.com \
    cloudbuild.googleapis.com

# Retrieve project number
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
DEFAULT_COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# 3. Self-healing for Default Build Service Account Role
echo -e "\n[*] Step 2: Ensuring the build service account has builder role (self-healing)..."
run_with_retry gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEFAULT_COMPUTE_SA}" \
    --role="roles/cloudbuild.builds.builder" \
    --quiet

# 4. Create Cloud Storage Bucket
echo -e "\n[*] Step 3: Creating Google Cloud Storage bucket for persistence..."
if gsutil ls -p "${PROJECT_ID}" "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
    echo "[+] Bucket gs://${BUCKET_NAME} already exists. Skipping creation."
else
    gsutil mb -c standard -l "${REGION}" -p "${PROJECT_ID}" "gs://${BUCKET_NAME}"
    echo "[+] Created bucket: gs://${BUCKET_NAME}"
fi

# 5. Configure Custom RUNNER Service Account (Execution Least-Privilege)
echo -e "\n[*] Step 4: Configuring custom RUNNER service account (${RUNNER_SA})..."
if gcloud iam service-accounts describe "${RUNNER_SA_EMAIL}" >/dev/null 2>&1; then
    echo "[+] Runner service account already exists."
else
    gcloud iam service-accounts create "${RUNNER_SA}" \
        --description="Executes the Frontier Pulse Cloud Function with secure least-privilege permissions" \
        --display-name="Frontier Pulse Runner" \
        --quiet
    echo "[+] Created service account: ${RUNNER_SA_EMAIL}"
fi

# Grant necessary GCS Bucket permissions (Wrapped with retry to handle IAM propagation delay)
echo "[*] Granting Storage Object Admin privileges on gs://${BUCKET_NAME}..."
run_with_retry gsutil iam ch "serviceAccount:${RUNNER_SA_EMAIL}:roles/storage.objectAdmin" "gs://${BUCKET_NAME}"

# Grant Secret Access privileges (Wrapped with retry to handle IAM propagation delay)
echo "[*] Granting Secret Manager Accessor role at project level..."
run_with_retry gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUNNER_SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet

# Grant Log Writing privileges (Wrapped with retry to handle IAM propagation delay)
echo "[*] Granting Cloud Logging Log Writer role at project level..."
run_with_retry gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUNNER_SA_EMAIL}" \
    --role="roles/logging.logWriter" \
    --quiet

# Grant Vertex AI User privileges (Wrapped with retry to handle IAM propagation delay)
echo "[*] Granting Vertex AI User role at project level..."
run_with_retry gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUNNER_SA_EMAIL}" \
    --role="roles/aiplatform.user" \
    --quiet

# 6. Initialize Secrets in Secret Manager
echo -e "\n[*] Step 5: Initializing secrets in Secret Manager (if missing)..."
init_secret() {
    local secret_name=$1
    if gcloud secrets describe "${secret_name}" >/dev/null 2>&1; then
        echo "[+] Secret '${secret_name}' already exists."
    else
        gcloud secrets create "${secret_name}" --replication-policy="automatic" --data-file=- <<< "PLACEHOLDER"
        echo "[+] Created empty secret: '${secret_name}'."
    fi
}

init_secret "GEMINI_API_KEY"
init_secret "TELEGRAM_BOT_TOKEN"
init_secret "TELEGRAM_CHAT_ID"

echo -e "\n>>> IMPORTANT: Ensure secrets GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, and TELEGRAM_CHAT_ID"
echo -e "    have their actual API tokens added as 'latest' versions in the GCP Console under Secret Manager."

# 7. Configure Custom INVOKER Service Account (Trigger Least-Privilege)
echo -e "\n[*] Step 6: Configuring custom INVOKER service account (${INVOKER_SA})..."
if gcloud iam service-accounts describe "${INVOKER_SA_EMAIL}" >/dev/null 2>&1; then
    echo "[+] Invoker service account already exists."
else
    gcloud iam service-accounts create "${INVOKER_SA}" \
        --description="Invokes the Frontier Pulse weekly function from Cloud Scheduler safely" \
        --display-name="Frontier Pulse Invoker" \
        --quiet
    echo "[+] Created service account: ${INVOKER_SA_EMAIL}"
fi

# 8. Deploy Cloud Run Function Gen 2 as Custom Runner SA
echo -e "\n[*] Step 7: Deploying Cloud Run Function Gen 2 (${FUNCTION_NAME})...."
echo "[*] Packaging and deploying with service account ${RUNNER_SA_EMAIL}..."

gcloud functions deploy "${FUNCTION_NAME}" \
    --gen2 \
    --runtime=python311 \
    --region="${REGION}" \
    --entry-point=run_edition_gcf \
    --trigger-http \
    --no-allow-unauthenticated \
    --ingress-settings=all \
    --service-account="${RUNNER_SA_EMAIL}" \
    --set-env-vars="GCS_BUCKET_NAME=${BUCKET_NAME},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},USE_VERTEX_AI=true,PODCAST_VOICE_NAME=es-US-Chirp-HD-O" \
    --set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest" \
    --timeout=1200s \
    --memory=1Gi

# Retrieve function URL
FUNCTION_URL=$(gcloud functions describe "${FUNCTION_NAME}" --region="${REGION}" --format="value(url)")
echo "[+] Cloud Function deployed successfully at: ${FUNCTION_URL}"

# Grant Invoker privileges to Scheduler service account (Wrapped with retry to handle IAM propagation delay)
echo -e "\n[*] Step 8: Granting Invoker privileges to Scheduler service account..."
run_with_retry gcloud run services add-iam-policy-binding "${FUNCTION_NAME}" \
    --region="${REGION}" \
    --member="serviceAccount:${INVOKER_SA_EMAIL}" \
    --role="roles/run.invoker" \
    --quiet

# 9. Create Cloud Scheduler trigger
echo -e "\n[*] Step 9: Configuring Cloud Scheduler Weekly Job..."
echo "[*] Trigger scheduled for: Every Monday at 5:00 PM (17:00) America/Bogota Timezone"

# Delete job if it already exists to recreate with latest URL
if gcloud scheduler jobs describe "${SCHEDULER_JOB_NAME}" --location="${REGION}" >/dev/null 2>&1; then
    echo "[*] Recreating existing Cloud Scheduler job..."
    gcloud scheduler jobs delete "${SCHEDULER_JOB_NAME}" --location="${REGION}" --quiet
fi

gcloud scheduler jobs create http "${SCHEDULER_JOB_NAME}" \
    --schedule="0 17 * * 1" \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --time-zone="America/Bogota" \
    --location="${REGION}" \
    --oidc-service-account-email="${INVOKER_SA_EMAIL}" \
    --oidc-token-audience="${FUNCTION_URL}" \
    --quiet

echo -e "\n================================================================="
echo -e "[+] DEPLOYMENT COMPLETED SUCCESSFULLY WITH CUSTOM SAs!"
echo -e "================================================================="
echo -e "Summary of deployed services:"
echo -e "  1. Cloud Storage Bucket: gs://${BUCKET_NAME}"
echo -e "  2. Secret Manager Credentials: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
echo -e "  3. Custom Runner SA (Execution): ${RUNNER_SA_EMAIL}"
echo -e "  4. Custom Invoker SA (Trigger): ${INVOKER_SA_EMAIL}"
echo -e "  5. Cloud Run Function: ${FUNCTION_NAME} at ${FUNCTION_URL}"
echo -e "  6. Cloud Scheduler Job: Triggering weekly on Mondays at 5:00 PM (America/Bogota)"
echo -e "================================================================="
