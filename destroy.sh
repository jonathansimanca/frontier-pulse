#!/usr/bin/env bash
# ==============================================================================
#      FRONTIER PULSE - GCP SERVERLESS CLEANUP SCRIPT (DESTROY)
# ==============================================================================
# This script dismantles and purges all GCP resources provisioned by the 
# deploy.sh script to leave your sandbox environment completely pristine.
#
# Highly resilient: Includes automatic retry loops with exponential backoff
# to bypass transient GCP lock errors (such as "sync mutate calls cannot be queued"),
# while intelligently skipping missing resources immediately without waiting.
#
# Usage:
#   chmod +x destroy.sh
#   ./destroy.sh <GCP_PROJECT_ID>
# ==============================================================================

set -eo pipefail

# 1. Configuration & Argument Parsing
PROJECT_ID=$1
if [ -z "$PROJECT_ID" ]; then
    echo -e "\n[!] Error: Please provide your GCP Project ID."
    echo -e "Usage:\n  ./destroy.sh <GCP_PROJECT_ID>\n"
    exit 1
fi

REGION="us-central1"
FUNCTION_NAME="frontier-pulse-weekly"
BUCKET_NAME="frontier-pulse-data-${PROJECT_ID}"
SCHEDULER_JOB_NAME="frontier-pulse-trigger"

# Custom Service Account Emails
RUNNER_SA="frontier-pulse-runner"
RUNNER_SA_EMAIL="${RUNNER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

INVOKER_SA="frontier-pulse-invoker"
INVOKER_SA_EMAIL="${INVOKER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "================================================================="
echo "  WARNING: THIS WILL DESTROY ALL FRONTIER PULSE RESOURCES IN GCP"
echo "  Project Target: ${PROJECT_ID}"
echo "  Region: ${REGION}"
echo "================================================================="

# Set active project
gcloud config set project "${PROJECT_ID}"

# Helper function to run commands with retries and exponential backoff.
# Intelligently detects if a resource is missing ("not found") and skips instantly
# to avoid unnecessary retries, while retrying on transient GCP congestion/locks.
run_with_retry() {
    local max_attempts=4
    local attempt=1
    local delay=2
    local stderr_log

    stderr_log=$(mktemp)

    until "$@" 2>"$stderr_log"; do
        # If the error output indicates the resource is missing/already deleted, skip immediately
        if grep -q -i -E "not found|notfound|notexist|does not exist|bucket_not_found|status=404" "$stderr_log"; then
            echo "[*] Resource already deleted or not found. Skipping."
            rm -f "$stderr_log"
            return 0
        fi

        if (( attempt == max_attempts )); then
            echo "[!] Error: Action failed after $max_attempts attempts."
            cat "$stderr_log"
            rm -f "$stderr_log"
            return 1
        fi
        echo "[!] Action failed due to transient GCP congestion. Retrying in $delay seconds (Attempt $attempt/$max_attempts)..."
        sleep $delay
        ((attempt++))
        ((delay*=2))
    done
    rm -f "$stderr_log"
    return 0
}

# Disable exit on error to ensure we attempt to clean up all other resources even if one fails
set +e

# 2. Delete Cloud Scheduler Trigger
echo -e "\n[*] Step 1: Dismantling Cloud Scheduler trigger..."
echo "[*] Deleting job '${SCHEDULER_JOB_NAME}'..."
run_with_retry gcloud scheduler jobs delete "${SCHEDULER_JOB_NAME}" --location="${REGION}" --quiet

# 3. Delete Cloud Run Function Gen 2
echo -e "\n[*] Step 2: Dismantling Cloud Run Function Gen 2 (${FUNCTION_NAME})..."
echo "[*] Deleting Cloud Function '${FUNCTION_NAME}'..."
run_with_retry gcloud functions delete "${FUNCTION_NAME}" --region="${REGION}" --gen2 --quiet

# 4. Delete Cloud Storage Bucket recursively
echo -e "\n[*] Step 3: Purging persistent Cloud Storage bucket (gs://${BUCKET_NAME})..."
echo "[*] Deleting all files inside gs://${BUCKET_NAME} and removing bucket..."
# gsutil rm -r returns non-zero if the bucket is not found, which we handle
run_with_retry gsutil rm -r "gs://${BUCKET_NAME}"

# 5. Delete Custom Service Accounts and IAM bindings
echo -e "\n[*] Step 4: Dismantling Custom Service Accounts..."

echo "[*] Deleting service account '${RUNNER_SA_EMAIL}'..."
run_with_retry gcloud iam service-accounts delete "${RUNNER_SA_EMAIL}" --quiet

echo "[*] Deleting service account '${INVOKER_SA_EMAIL}'..."
run_with_retry gcloud iam service-accounts delete "${INVOKER_SA_EMAIL}" --quiet

# 6. Delete Secret Manager Secrets
echo -e "\n[*] Step 5: Purging Secret Manager secrets..."

echo "[*] Deleting secret 'GEMINI_API_KEY'..."
run_with_retry gcloud secrets delete "GEMINI_API_KEY" --quiet

echo "[*] Deleting secret 'TELEGRAM_BOT_TOKEN'..."
run_with_retry gcloud secrets delete "TELEGRAM_BOT_TOKEN" --quiet

echo "[*] Deleting secret 'TELEGRAM_CHAT_ID'..."
run_with_retry gcloud secrets delete "TELEGRAM_CHAT_ID" --quiet

echo -e "\n================================================================="
echo -e "[+] CLEANUP AND DESTRUCTION COMPLETED SUCCESSFULLY!"
echo -e "================================================================="
echo -e "  Your GCP sandbox project is now completely clean of all"
echo -e "  Frontier Pulse infrastructure. No lingering charges will occur."
echo -e "================================================================="
