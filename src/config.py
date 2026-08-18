import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Main project directories
BASE_DIR = Path(__file__).resolve().parent.parent

# Check if running in Google Cloud Run / GCF
IS_CLOUD = os.getenv("K_SERVICE") is not None or os.getenv("FUNCTION_TARGET") is not None or os.getenv("FORCE_SERVERLESS") is not None

if IS_CLOUD:
    INPUT_DIR = Path("/tmp/input")
    OUTPUT_DIR = Path("/tmp/output")
else:
    INPUT_DIR = BASE_DIR / "input"
    OUTPUT_DIR = BASE_DIR / "output"

# Ensure directories exist
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def get_edition_dir(edition_date: str) -> Path:
    """Return the absolute path for the directory of a specific edition, ensuring it exists."""
    edition_dir = OUTPUT_DIR / "editions" / edition_date
    edition_dir.mkdir(parents=True, exist_ok=True)
    return edition_dir

# GCP & Vertex AI Configuration
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT", "")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
USE_VERTEX_AI = os.getenv("USE_VERTEX_AI", "true").lower() in ("true", "1", "yes")

# Optional Gemini Developer API Key fallback
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def get_genai_client():
    """Initialize Google GenAI client prioritizing Vertex AI on GCP with ADC or fallback to Gemini Developer API Key."""
    import sys
    from google import genai
    from google.genai import types
    from google.auth.exceptions import DefaultCredentialsError

    http_opts = types.HttpOptions(timeout=60000)

    if USE_VERTEX_AI or not GEMINI_API_KEY:
        print(f"[*] Authenticating with Vertex AI (project={GOOGLE_CLOUD_PROJECT or 'default ADC'}, location={GOOGLE_CLOUD_LOCATION})...")
        try:
            if GOOGLE_CLOUD_PROJECT:
                return genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT, location=GOOGLE_CLOUD_LOCATION, http_options=http_opts)
            else:
                return genai.Client(vertexai=True, location=GOOGLE_CLOUD_LOCATION, http_options=http_opts)
        except DefaultCredentialsError:
            if GEMINI_API_KEY:
                print("[!] Vertex AI ADC not found, falling back to GEMINI_API_KEY...")
                return genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts)
            print("\n[!] AUTHENTICATION ERROR:")
            print("Google Cloud Application Default Credentials (ADC) not found.")
            print("Run the following command in your terminal to authenticate with your GCP project:")
            print("   gcloud auth application-default login")
            print("Or set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json\n")
            sys.exit(1)
        except Exception as e:
            if GEMINI_API_KEY:
                print(f"[!] Vertex AI connection failed ({e}), falling back to GEMINI_API_KEY...")
                return genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts)
            raise

    print("[*] Authenticating with Gemini Developer API Key...")
    return genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_TIMEOUT = int(os.getenv("TELEGRAM_TIMEOUT", "35"))
TELEGRAM_RETRIES = int(os.getenv("TELEGRAM_RETRIES", "3"))
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "") or os.getenv("HTTPS_PROXY", "") or os.getenv("HTTP_PROXY", "")
TELEGRAM_STRICT = os.getenv("TELEGRAM_STRICT", "false").lower() in ("true", "1", "yes")

# Podcast Configuration
PODCAST_LANGUAGE_ES = "es-US"  # Latin American Spanish
PODCAST_LANGUAGE_EN = "en-US"
PODCAST_VOICE_NAME = os.getenv("PODCAST_VOICE_NAME", "es-US-Chirp-HD-O")  # High-definition Latin American Spanish voice
PODCAST_MAX_DURATION_MINUTES = 5
PODCAST_FORMAT = "monologue"

# Model Configuration (Standard Vertex AI and Gemini API compatible models)
GEMINI_RESEARCH_MODEL = os.getenv("GEMINI_RESEARCH_MODEL", "gemini-2.5-flash")
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
MAX_API_RETRIES = 2

# Research Tracks for Multi-Track Discovery
RESEARCH_TRACKS = {
    "frontier_labs": [
        "Google Gemini DeepMind release announcement",
        "OpenAI GPT launch model update announcement",
        "Anthropic Claude release update",
        "DeepSeek model reasoning release",
        "Meta Llama release open weights",
        "xAI Grok release update",
    ],
    "agentic_and_dev": [
        "AI coding agents benchmark autonomous tools",
        "Computer Use autonomous agent API frameworks",
        "Developer tools API SDK Gemini Claude OpenAI",
    ],
    "infrastructure_and_hardware": [
        "AI hardware chips Cerebras Nvidia Groq datacenter",
        "AI lab executive leadership restructuring valuation",
    ],
    "open_source": [
        "Open source LLM weights release HuggingFace Qwen Kimi DeepSeek",
    ],
}

# Clean consolidated priority topics
PRIORITY_TOPICS = [
    "Google Gemini & DeepMind",
    "OpenAI & GPT models",
    "Anthropic & Claude",
    "DeepSeek & Open-Weight Reasoning Models",
    "Meta Llama & Open-Source LLMs (Qwen, Kimi)",
    "Autonomous AI Agents, Coding & Computer Use",
    "AI Hardware & Infrastructure (Cerebras, Groq, Nvidia)",
    "AI Security & Governance",
]

# Source domain filtering
BLOCKED_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "capitalbench.com",
    "pinterest.com",
    "reddit.com",
]

AUTHORITATIVE_DOMAINS = [
    "blog.google",
    "deepmind.google",
    "openai.com",
    "anthropic.com",
    "deepseek.com",
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "reuters.com",
    "venturebeat.com",
    "huggingface.co",
    "wired.com",
]
