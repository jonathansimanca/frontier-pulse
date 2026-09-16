# Frontier Pulse

A personal technology watch agent that automatically researches weekly Artificial Intelligence developments, designs multi-image visual cards and cover art, converts the summaries into high-quality spoken audio podcasts, and delivers them directly to Telegram.

The system is deployed on Google Cloud Platform (Cloud Run Functions Gen 2 + Cloud Scheduler + Secret Manager) and runs automatically every Monday at 5:00 PM Bogotá time. It is also fully compatible with local development runs via `uv`.

---

## 🚀 Key Features

1. **Multi-Track AI Web Research (Gemini Search Grounding):** Priority-driven, multi-track web discovery exploring key AI tracks concurrently:
   - *Frontier Labs & Flagships:* Google DeepMind (Gemini, Project Astra), OpenAI, Anthropic (Claude), DeepSeek, Meta AI, xAI, Mistral.
   - *Agentic Frameworks & Developer Tooling:* Coding agents, Computer Use, Model Context Protocol (MCP), APIs.
   - *Hardware & Infrastructure:* AI acceleration (Nvidia, Cerebras, Groq, TPUs, Trainium), mega-datacenter energy, and lab restructuring.
   - *Open Source & Open Weights:* Hugging Face, Alibaba Qwen / QwQ, Kimi, DeepSeek, and Meta Llama releases.
   - *Frontier Safety & Governance:* Coordinated actions and joint statements by frontier labs, calls to slow down or pause frontier AI development, capability limits, risk thresholds, independent/embedded evaluators, and international safety agreements.

   Each track has its own discovery focus (`TRACK_DISCOVERY_FOCUS` in `src/config.py`). Candidates are validated one by one, and the discovery pool is capped fairly across tracks.
2. **Deterministic Deduplication & History Tracking:** Deduplicates candidates against historical editions using normalized source URLs and title similarity.
3. **4-Tier Editorial Selection Rubric:** Ranks candidates into Tiers (Tier 1 flagship releases, breakthrough infrastructure, and multi-lab safety/governance developments; Tier 2 open weights, dev tools, safety-policy and regulatory changes, and funding/partnerships at most; Tier 3 minor patches; Tier 4 rejected spam and portfolios).
4. **Multi-Lab Safety Priority Guard (`src/editorial_priority.py`):** A deterministic classifier flags candidates that name at least two frontier labs together with a specific safety/governance action (e.g. slowdown, pause, joint commitment, risk thresholds). Flagged candidates are highlighted to the editor model, and if one is still omitted, the guard appends at most one (only with an authoritative source, only when the edition has fewer than 5 stories, and never as a duplicate of an already selected flagged story).
5. **Source Link Check (`src/source_link_checker.py`):** Verifies the source links of selected stories and flagged candidates over HTTP, removes broken links (404/410 or unresolvable domains), and drops stories left without a working link. Publisher bot blocks and timeouts never count as broken. Set `LINK_CHECK_ENABLED=false` to disable.
6. **Factual Claim Check (`src/claim_verifier.py`):** Prompts require source-faithful attribution, and one grounded Gemini call fact-checks the selected stories after selection, correcting only their text (never ids, sources, or scores) and keeping the original text if the check fails. Set `CLAIM_CHECK_ENABLED=false` to disable.
7. **Research Audit Trail (`src/research_audit.py`):** Every run writes `output/editions/<date>/research_audit.json` with each track's queries, prompt, model attempts, grounding searches and sources, and every candidate's final outcome and reason, so a missed story can be traced to discovery, filtering, or ranking.
8. **Editorial Quality Gate (`src/quality_gate.py`):** Multi-rule verification checking domain trustworthiness, temporal window compliance, and publisher diversity.
9. **Analytical Monologue Scripting & Phonetic Normalization (`src/script_generator.py`):** Produces a fast-paced, analytical 7-step monologue script (Opening hook, Main announcement, Technical details & benchmarks, Competitor comparisons, Strategic implications, Industry trends, and Concluding audience question) with phonetic text normalization for spoken Spanish.
10. **Multi-Image Visual Asset Generation (`src/visual_asset_generator.py`):** Generates 2–3 portrait $1080 \times 1350\text{ px}$ (4:5) cards combining AI background artwork (`gemini-3.1-flash-image` / Imagen 3) with a deterministic Pillow compositing layer (safe margins $\ge 80\text{ px}$, scalable typography, dark translucent cards, and high-contrast badges) plus an `edition-[YYYY-MM-DD]-assets.json` manifest formatted for mobile video editing and LinkedIn carousels:
   - **AR-01 Cover Card:** Headline $\le 10$ words, release date, audio duration, and call-to-action.
   - **AR-02 Primary News Insight Card:** Plain-language title $\le 9$ words, key fact $\le 20$ words, and why it matters $\le 16$ words.
   - **AR-03 Secondary News Insight Card (Optional):** Structured card for a distinct secondary story.
11. **High-Definition es-US Spoken Audio (Google Cloud Text-to-Speech):** Synthesizes Latin American Spanish audio using the HD voice (`es-US-Chirp-HD-O`) with sentence-boundary chunking for seamless long-form audio.
12. **Dual Transcripts:** Automatically produces structured, clean written transcripts in both Latin American Spanish and English.
13. **Idempotent Telegram Publisher with Media Group Album (`src/telegram_publisher.py`):** Delivers the formatted markdown bulletin, all generated visual cards as a swipeable photo album (media group), and the final `.mp3` episode to your Telegram chat/channel with atomic manifest checkpoints.

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

Run unit and integration tests:
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
