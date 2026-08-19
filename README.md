# Frontier Pulse

Personal technology watch agent that automatically researches weekly Artificial Intelligence developments, designs dynamic visual cover arts, converts the summaries into high-quality spoken audio podcasts, and delivers them directly to Telegram.

Compatible with both **local development runs** (cached via local JSON transactions) and **fully serverless cloud deployments** (Google Cloud Run Functions Gen 2 + Cloud Storage sync + Secret Manager).

---

## 🚀 Key Features

1. **Multi-Track AI Web Research (Gemini Search Grounding):** Priority-driven, multi-track web discovery exploring four distinct tracks concurrently:
   - *Frontier Labs & Flagships:* Google DeepMind (Project Astra, Gemini), OpenAI, Anthropic (Claude), DeepSeek, Meta AI, xAI.
   - *Agentic Frameworks & Developer Tooling:* Coding agents, Computer Use, APIs, multimodal execution.
   - *Hardware & Infrastructure:* AI acceleration (Cerebras, Nvidia, Groq), custom inference silicon, and lab restructuring.
   - *Open Source & Open Weights:* HuggingFace, Qwen, Kimi, DeepSeek, and Llama releases.
2. **Deterministic Deduplication & History Tracking:** Deduplicates candidates against historical editions using normalized source URLs and title similarity.
3. **4-Tier Editorial Selection Rubric:** Rigorously ranks candidates into Tiers (Tier 1 Flagship Releases & Infrastructure, Tier 2 Open Weights & Dev Tools, Tier 3 Minor Patches, Tier 4 Rejected Spam & Portfolios).
4. **Editorial Quality Gate (`src/quality_gate.py`):** Multi-rule verification checking domain trustworthiness, temporal window compliance, and publisher diversity.
5. **Analytical Monologue Scripting & Phonetic Normalization (`src/script_generator.py`):** Produces a fast-paced, analytical 7-step monologue script (Opening hook, Main announcement, Technical details & benchmarks, Competitor comparisons, Strategic implications, Industry trends, and Concluding audience question) with phonetic text normalization for spoken Spanish.
6. **AI Generated Cover Art (`src/image_generator.py`):** Generates vertical 9:16 podcast cover art matching the edition's news themes using Gemini multimodal image generation (`gemini-3.1-flash-image`).
7. **High-Definition es-US Spoken Audio (Google Cloud Text-to-Speech):** Synthesizes Latin American Spanish audio using the HD voice (`es-US-Chirp-HD-O`) with sentence-boundary chunking for seamless long-form audio.
8. **Dual Transcripts:** Automatically produces structured, clean written transcripts in both Latin American Spanish and English.
9. **Idempotent Telegram Publisher:** Delivers the formatted markdown bulletin, the vertical cover poster, and the final `.mp3` episode to your Telegram chat/channel with atomic manifest checkpoints.

---

## 🛠️ Local Development Quickstart

### Prerequisites
- **Python**: `3.10+` (developed and verified on `3.11` and `3.14`)
- **Google Gemini API Key**: Set `GEMINI_API_KEY` in your `.env` for LLM research, script generation, and cover art creation.
- **Google Cloud Auth (for TTS and GCS sync)**: Authenticate your terminal with Google Application Default Credentials (ADC) to access GCP Text-to-Speech and Cloud Storage:
  ```bash
  gcloud auth application-default login
  ```

### Installation
1. Install project dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

2. Configure environment variables (`.env`):
   Copy `.env.example` to `.env` and fill in your configuration:
   ```env
   # Google Gemini Developer API Key (Required)
   GEMINI_API_KEY=your_gemini_api_key_here

   # Google Cloud Project (used for Cloud Storage persistence and Text-to-Speech)
   GOOGLE_CLOUD_PROJECT=your-gcp-project-id
   GOOGLE_CLOUD_LOCATION=us-central1

   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=7123456789:AAHzX89_example_token
   TELEGRAM_CHAT_ID=-1001234567890
   ```

### Running Locally
Run the entire end-to-end pipeline:
```bash
python3 -m src.main
```

Run unit and integration tests (29 passing tests):
```bash
pytest -v
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
