# Frontier Pulse

Personal technology watch agent that automatically researches weekly Artificial Intelligence developments, designs dynamic visual cover arts, converts the summaries into high-quality spoken audio podcasts, and delivers them directly to Telegram.

Compatible with both **local development runs** (cached via local JSON transactions) and **fully serverless cloud deployments** (Google Cloud Run Functions Gen 2 + Cloud Storage sync + Secret Manager).

---

## 🚀 Key Features

1. **Intelligent AI Web Research (Gemini Search Grounding):** Priority-driven web exploration across nine core AI topics with automated deduplication against the last 4 weeks of history.
2. **Editorial Quality Gate (`src/quality_gate.py`):** Multi-rule content checking verifying topic relevance, validity of citations/links, and date compliance before proceeding.
3. **Phonetic TTS Text Normalization (`src/script_generator.py`):** Dynamic phonetic transcript conversion translating numbers, dates, version numbers, and technical acronyms into fully spoken Spanish words.
4. **Fotorrealistic Cover Art (Nano Banana Image Gen):** Reviews the week's chosen news stories and generates vertical cover art using the **Interactions API** of the **`gemini-3.1-flash-image`** model.
5. **High-Fidelity es-US Spoken Audio (GCP Text-to-Speech):** Synthesizes natural, high-fidelity spoken Latin American Spanish audio using Google Cloud Neural2 voices.
6. **Dual Transcripts:** Automatically produces fully-formed, clean written transcripts in both Latin American Spanish and English.
7. **Idempotent Telegram Publisher:** Delivers the formatted markdown bulletin, the vertical fotorrealistic cover poster, and the final `.mp3` episode to your Telegram chat/channel. Supports resuming from failures dynamically.

---

## 🛠️ Local Development Quickstart

### Prerequisites
- **Python**: `3.10+` (developed and verified on `3.11` and `3.14`)
- **Package Manager**: `uv`
- **Google Cloud Auth**: Authenticate your terminal with Google Application Default Credentials (ADC) to access GCP Text-to-Speech:
  ```bash
  gcloud auth application-default login
  ```

### Installation
1. Sync project dependencies:
   ```bash
   uv sync
   ```

2. Configure environment variables (`.env`):
   Create a `.env` file in the root directory:
   ```env
   # Gemini API Credentials (required for research, scripting, and images)
   GEMINI_API_KEY=your_gemini_api_key

   # Telegram Bot Delivery Configs (required to send to Telegram)
   TELEGRAM_BOT_TOKEN=7123456789:AAHzX89_example_token
   TELEGRAM_CHAT_ID=-1001234567890
   ```

### Running Locally
Run the entire end-to-end pipeline:
```bash
uv run python -m src.main
```

Run unit and integration tests (27 passing tests):
```bash
uv run --no-project --with pytest --with pydantic --with requests --with google-genai --with python-dotenv --with google-cloud-storage --with functions-framework python -m pytest
```

---

## ☁️ Google Cloud Serverless Deployment

Frontier Pulse is designed to deploy serverless to GCP using a secure, least-privilege custom Service Account framework and restricted ingress.

```
[Cloud Scheduler (America/Bogota)]
             │
             ▼ (Trigger internal HTTP POST with OIDC SA Token)
[Cloud Run Functions Gen 2] ◄── [Secret Manager (Credentials)]
      │             │
      ▼ (Sync-Start)▼ (Sync-Success)
[GCS Bucket (gs://frontier-pulse-data)]
```

### Automatic Provisioning & Deployment
1. Ensure your terminal is authenticated with your GCP account:
   ```bash
   gcloud auth login
   ```

2. Run the deployment script to provision services, custom runner/invoker service accounts, Secret Manager configurations, the Cloud Storage bucket, the Cloud Function, and the Cloud Scheduler job (scheduled for **every Monday at 5:00 PM Bogotá time**):
   ```bash
   chmod +x deploy.sh
   ./deploy.sh <YOUR_GCP_PROJECT_ID>
   ```

3. Open **Secret Manager** in your Google Cloud Console, and update the secrets (`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID`) by creating new versions containing your real tokens.

4. Run the deployment script once more to force Cloud Run to trigger a new revision cold-start and bind your real secret credentials:
   ```bash
   ./deploy.sh <YOUR_GCP_PROJECT_ID>
   ```

### Teardown & Sandbox Cleanup
To wipe out all provisioned resources (Storage bucket, Cloud Function, custom SAs, secrets, and Cloud Scheduler triggers) cleanly without leaving any orphan costs:
```bash
chmod +x destroy.sh
./destroy.sh <YOUR_GCP_PROJECT_ID>
```
*(The teardown script features automatic exponential backoff to handle transient Google API synchronization locks gracefully).*
