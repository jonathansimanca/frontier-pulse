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

from datetime import datetime, timezone, timedelta

# Timezone Configuration (America/Bogota UTC-5)
BOGOTA_TZ = timezone(timedelta(hours=-5))

def get_current_edition_date() -> str:
    """Return the current edition date in America/Bogota timezone (YYYY-MM-DD)."""
    return datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")

def get_edition_dir(edition_date: str) -> Path:
    """Return the absolute path for the directory of a specific edition, ensuring it exists."""
    edition_dir = OUTPUT_DIR / "editions" / edition_date
    edition_dir.mkdir(parents=True, exist_ok=True)
    return edition_dir

# GCP Configuration
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT", "")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# Google Gemini API Key
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")


def get_genai_client():
    """Initialize Google GenAI client with Gemini Developer API Key."""
    import sys
    from google import genai
    from google.genai import types

    http_opts = types.HttpOptions(timeout=60000)

    clean_key = (os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY).strip().strip('"').strip("'")

    if not clean_key:
        print("\n[!] AUTHENTICATION ERROR:")
        print("GEMINI_API_KEY environment variable is not set.")
        print("Please set your Gemini Developer API Key in your .env file or environment:\n")
        print("   GEMINI_API_KEY=your_gemini_api_key_here\n")
        sys.exit(1)

    print("[*] Authenticating with Gemini Developer API Key...")
    return genai.Client(api_key=clean_key, http_options=http_opts)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip().strip('"').strip("'")
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip().strip('"').strip("'")
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

# Model Configuration (Gemini API models)
GEMINI_RESEARCH_MODEL = os.getenv("GEMINI_RESEARCH_MODEL", "gemini-3.7-flash")
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-3.7-flash")
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
