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
# HTTP verification of source links for selected stories and flagged priority candidates.
LINK_CHECK_ENABLED = os.getenv("LINK_CHECK_ENABLED", "true").lower() in ("true", "1", "yes")
LINK_CHECK_TIMEOUT_SECONDS = float(os.getenv("LINK_CHECK_TIMEOUT_SECONDS", "5"))
LINK_CHECK_MAX_WORKERS = int(os.getenv("LINK_CHECK_MAX_WORKERS", "6"))
# Single grounded fact-check of the selected stories after editorial selection.
CLAIM_CHECK_ENABLED = os.getenv("CLAIM_CHECK_ENABLED", "true").lower() in ("true", "1", "yes")
# Model used for discovery retries after the first attempt of a research track fails.
GEMINI_RESEARCH_FALLBACK_MODEL = os.getenv("GEMINI_RESEARCH_FALLBACK_MODEL", "gemini-3.6-flash")
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-3.7-flash")
MAX_API_RETRIES = 2

# Research Tracks for Multi-Track Discovery
RESEARCH_TRACKS = {
    # 1. Major Frontier Labs & Flagship Foundation Models
    # Queries intentionally avoid pinning specific model versions (e.g. "o1 o3", "V3 R1"),
    # which bias grounded search toward stale coverage as model generations move on.
    "frontier_labs": [
        "Google DeepMind Gemini new model announcement",
        "OpenAI new model launch or major product announcement",
        "Anthropic Claude new model launch or major product announcement",
        "DeepSeek new model release announcement",
        "xAI Grok new model release announcement",
        "Mistral AI new model release announcement",
    ],

    # 2. Autonomous Agents, Coding Systems & Protocol Standards
    "agentic_and_dev": [
        "Autonomous AI coding agents SWE-bench benchmarks Cursor Devin Windsurf",
        "Computer Use GUI browser autonomous agent framework",
        "Model Context Protocol MCP Agent-to-Agent A2A protocol SDK",
        "OpenAI Anthropic Gemini Realtime Live API developer tooling",
    ],

    # 3. Open-Weights, Global LLMs & Efficient On-Device Inference
    "open_source_and_global": [
        "Meta Llama open weights model release benchmark",
        "Alibaba Qwen QwQ reasoning model open release",
        "Moonshot Kimi Zhipu GLM 01.AI open LLM release",
        "Hugging Face open source models trending leaderboard",
        "Local LLM inference vLLM SGLang Ollama on-device SLM Apple Intelligence",
    ],

    # 4. Multimodal Generation & World Models (Video, Voice, 3D)
    "multimodal_and_creative": [
        "AI video generation Sora Veo Runway Kling Luma Hunyuan",
        "AI voice audio speech synthesis ElevenLabs Suno Udio",
        "Vision language multimodal reasoning 3D spatial world models",
    ],

    # 5. AI Hardware, Chips, Mega-Clusters & Datacenter Energy
    "infrastructure_and_hardware": [
        "Nvidia Blackwell Rubin GPU AI hardware architecture",
        "Custom AI chips Cerebras Groq Google TPU AWS Trainium",
        "AI datacenter energy nuclear power gigawatt compute infrastructure",
        "Frontier AI lab executive leadership restructuring acquisition valuation",
    ],

    # 6. Evaluation Benchmarks, Technical Safety, Security & Regulation
    "benchmarks_safety_and_policy": [
        "LMSYS Chatbot Arena LiveBench ARC-AGI benchmark leaderboard",
        "AI safety alignment reasoning jailbreak prompt injection defense",
        "AI regulation policy US AISI UK AISI EU AI Act compliance",
    ],

    # 7. Frontier AI Safety Governance, Lab Coordination & Development Pace
    # Covers developments that change the speed, safety, or oversight of frontier AI
    # (coordinated lab actions, slowdowns, capability limits, risk thresholds,
    # independent evaluations, and international agreements), which the product- and
    # technique-oriented tracks above do not surface.
    "frontier_safety_and_governance": [
        "Anthropic OpenAI xAI Google DeepMind leaders joint statement on frontier AI safety or development pace",
        "Frontier AI development slowdown pause halt moratorium or capability limits called for by AI labs",
        "Coordinated safety commitments between frontier AI labs Anthropic OpenAI Google DeepMind xAI Meta",
        "Frontier model risk thresholds catastrophic risk warning responsible scaling policy preparedness framework update",
        "Independent third-party safety evaluations embedded external evaluators pre-deployment testing of frontier models",
        "International AI safety agreement summit or governance coordination on frontier AI development",
    ],

    # 8. Frontier Safety Headlines (second, independent pass over the safety track's scope)
    # Short news-headline queries. Grounded search tends to rewrite the long descriptive
    # queries above into generic searches; on 2026-09-15 that missed the widely reported
    # call by frontier-lab CEOs to slow AI development. Overlap with track 7 is expected and
    # handled by in-pool title dedup, the same-event selection rule, and the priority guard.
    "frontier_safety_headlines": [
        "AI CEOs call for AI slowdown",
        "Altman Amodei Musk Hassabis AI warning",
        "AI labs pause or slow AI development",
        "AI stocks fall after AI safety warning",
        "AI companies joint AI safety pledge",
        "governments frontier AI safety agreement",
    ],
}

# Track-specific discovery focus injected into each discovery prompt.
# Without it, every track inherits a product-launch framing (releases, benchmarks,
# tooling) and statement- or commitment-type developments are ignored.
DEFAULT_TRACK_DISCOVERY_FOCUS = (
    "major official announcements, model releases, technical benchmarks, developer tooling, "
    "or key industry and infrastructure developments"
)

TRACK_DISCOVERY_FOCUS = {
    "frontier_labs": (
        "new or updated flagship models, major product launches, and strategic moves by frontier AI labs"
    ),
    "agentic_and_dev": (
        "autonomous agent systems, coding agents, agent protocols, and developer platforms with verified capabilities"
    ),
    "open_source_and_global": (
        "open-weight model releases, global (non-US) frontier LLMs, and efficient or on-device inference"
    ),
    "multimodal_and_creative": (
        "video, voice, music, vision-language, and world-model generation breakthroughs"
    ),
    "infrastructure_and_hardware": (
        "AI chips, compute clusters, datacenter energy, and frontier-lab corporate or leadership changes"
    ),
    "benchmarks_safety_and_policy": (
        "benchmark results, technical safety and security research, and AI regulation or compliance actions"
    ),
    "frontier_safety_and_governance": (
        "developments that materially change the speed, safety, or oversight of frontier AI: "
        "coordinated actions or joint statements by multiple frontier labs; calls for or decisions on a "
        "slowdown, pause, halt, moratorium, or capability limits; new or changed frontier-model risk "
        "thresholds, deployment thresholds, or catastrophic-risk warnings; independent or embedded external "
        "safety evaluations; voluntary safety commitments; and international AI safety agreements or "
        "government coordination. On-the-record public statements by frontier-lab CEOs, leading researchers, "
        "governments, or recognized AI safety organizations count as substantive developments"
    ),
    "frontier_safety_headlines": (
        "breaking news this period about the pace, safety, or oversight of frontier AI: frontier-lab CEOs or "
        "leading researchers calling for a slowdown, pause, or limits; joint safety pledges or commitments by AI "
        "companies; government agreements on frontier AI; and market or policy reactions to AI safety warnings. "
        "Report the underlying development, not the market reaction alone"
    ),
}

# Discovery candidate limits
MIN_CANDIDATES_PER_TRACK = 3
MAX_CANDIDATES_PER_TRACK = 6
# Must match DiscoveryEdition.items max_length in src/schemas.py.
MAX_DISCOVERY_POOL_SIZE = 35

# Clean consolidated priority topics
PRIORITY_TOPICS = [
    "Google DeepMind & Gemini Ecosystem (Astra, Veo, Gemma, AlphaFold)",
    "OpenAI & Frontier Reasoning (GPT, o-series, Operator, Sora)",
    "Anthropic & Claude Ecosystem (Computer Use, Artifacts, Tool-Use)",
    "DeepSeek & Open Reasoning Architecture (V3, R1, MoE Innovations)",
    "Meta AI & Open-Source Global Frontier (Llama, Qwen, Kimi, Mistral)",
    "Autonomous AI Agents, Coding Engines & Protocols (MCP, SWE-bench, Devin, Cursor)",
    "Generative Multimodal Media (Video World Models, Voice Synthesis, Vision-Language)",
    "AI Hardware, Acceleration & Clusters (Nvidia, Cerebras, Groq, TPU, Trainium, Datacenters)",
    "AI Safety, Alignment, Benchmarks & Global Governance (LMSYS Arena, AISI, Regulation)",
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
    # Official AI Labs
    "blog.google",
    "deepmind.google",
    "openai.com",
    "anthropic.com",
    "deepseek.com",
    "x.ai",
    "mistral.ai",
    "ai.meta.com",
    "huggingface.co",
    "cerebras.ai",
    "groq.com",
    "together.ai",
    # Authoritative Tech & Hardware Outlets
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "reuters.com",
    "venturebeat.com",
    "wired.com",
    "technologyreview.com",
    "theinformation.com",
    "semianalysis.com",
    "siliconangle.com",
    # Major general news outlets (used to verify safety/governance priority stories)
    "bloomberg.com",
    "ft.com",
    "nytimes.com",
    "wsj.com",
    "axios.com",
    "apnews.com",
    "cnbc.com",
    "theguardian.com",
    "bbc.com",
    "bbc.co.uk",
    # Government bodies and AI safety institutes
    "aisi.gov.uk",
    "nist.gov",
    "europa.eu",
    "whitehouse.gov",
    "frontiermodelforum.org",
]
