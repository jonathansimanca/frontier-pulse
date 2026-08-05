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

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Podcast Configuration
PODCAST_LANGUAGE_ES = "es-US"  # Latin American Spanish
PODCAST_LANGUAGE_EN = "en-US"
PODCAST_VOICE_NAME = "es-US-Neural2-B"  # High-quality Latin American Spanish male voice
PODCAST_MAX_DURATION_MINUTES = 5
PODCAST_FORMAT = "monologue"

# Priority topics and projects to explicitly track during research
PRIORITY_TOPICS = [
    "OpenAI ASTRA",
    "Google Gemini & DeepMind",
    "Claude & Anthropic",
    "OpenAI & GPT models",
    "Llama & Open-Source LLMs (DeepSeek, Qwen y Kimi.)",
    "Company Brain",
    "AI Security",
    "AI Governance",
    "Autonomous AI Agents & Computer Use",
]
