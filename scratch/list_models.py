import os
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize the client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = genai.Client()

print("[*] Listing all available Google GenAI models for your API key...")
try:
    for model in client.models.list():
        if "imagen" in model.name or "image" in model.name or "generate" in model.name:
            print(f" - {model.name} (Supported methods: {model.supported_actions})")
except Exception as e:
    print(f"[!] Error listing models: {e}")
