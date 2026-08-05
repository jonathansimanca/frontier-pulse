import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from google import genai
from google.genai import types
from google.auth.exceptions import DefaultCredentialsError

from src.config import (
    INPUT_DIR,
    OUTPUT_DIR,
    get_edition_dir,
    GEMINI_API_KEY,
    PRIORITY_TOPICS,
)
from src.schemas import Edition, DiscoveryEdition, NewsItem
from pydantic import ValidationError

# Directory for storing past weekly reports for deduplication
HISTORY_DIR = OUTPUT_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def load_recent_history_editions(limit: int = 4) -> list[dict]:
    """Load up to `limit` recent weekly report JSONs from the history directory."""
    if not HISTORY_DIR.exists():
        return []

    history_files = sorted(HISTORY_DIR.glob("history_*.json"), reverse=True)
    editions = []
    
    for path in history_files[:limit]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                editions.append(json.load(f))
        except Exception as e:
            print(f"[!] Warning: Failed to load history file {path.name}: {e}")
            
    # Fallback to sample_news.json if no history exists yet
    if not editions:
        sample_path = INPUT_DIR / "sample_news.json"
        if sample_path.exists():
            try:
                with open(sample_path, "r", encoding="utf-8") as f:
                    editions.append(json.load(f))
            except Exception as e:
                print(f"[!] Warning: Failed to load sample news: {e}")
                
    return editions


def extract_previous_topics(history_data: dict | None) -> list[str]:
    """Extract list of titles and topics from previous edition."""
    if not history_data or "items" not in history_data:
        return []

    previous_topics = []
    for item in history_data.get("items", []):
        title = item.get("title", "")
        summary = item.get("summary", "")
        if title:
            previous_topics.append(f"- {title}: {summary[:100]}...")
    return previous_topics


def save_history_entry(news_data: dict) -> Path:
    """Save the newly generated news report to the history directory."""
    edition_date = news_data.get("edition_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    history_file = HISTORY_DIR / f"history_{edition_date}.json"

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)

    print(f"[+] Saved current edition to history: {history_file}")
    return history_file


def get_genai_client() -> genai.Client:
    """Initialize Gemini client using API Key or Application Default Credentials (Vertex AI)."""
    if GEMINI_API_KEY:
        print("[*] Authenticating with Gemini API Key...")
        return genai.Client(api_key=GEMINI_API_KEY)

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    print("[*] Authenticating with GCP Application Default Credentials (Vertex AI)...")
    try:
        if project:
            return genai.Client(vertexai=True, project=project, location=location)
        else:
            return genai.Client(vertexai=True, location=location)
    except DefaultCredentialsError:
        print("\n[!] AUTHENTICATION ERROR:")
        print("Google Cloud Application Default Credentials (ADC) not found.")
        print("Run the following command in your terminal to authenticate:")
        print("   gcloud auth application-default login\n")
        sys.exit(1)


def calculate_edition_window(edition_date: str) -> tuple[str, str]:
    """Calculate the explicit 7-day research coverage window ending at the end of the target edition date.
    
    All times are computed relative to America/Bogota timezone (UTC-5).
    Example: For target edition date '2026-08-03', the window will cover:
      Start: 2026-07-27T00:00:00-05:00
      End:   2026-08-03T23:59:59-05:00
    """
    from datetime import datetime, timedelta
    dt = datetime.strptime(edition_date, "%Y-%m-%d")
    
    # Start date is exactly 7 days before
    start_dt = dt - timedelta(days=7)
    
    # Format explicitly with UTC-5 offset for America/Bogota
    start_str = f"{start_dt.strftime('%Y-%m-%d')}T00:00:00-05:00"
    end_str = f"{dt.strftime('%Y-%m-%d')}T23:59:59-05:00"
    
    return start_str, end_str


def build_discovery_prompt(previous_topics: list[str], edition_date: str, start_date: str, end_date: str) -> str:
    """Build Discovery Stage prompt with explicit coverage window tracking, Search Grounding, and candidate instructions."""
    priority_str = "\n".join([f"- {topic}" for topic in PRIORITY_TOPICS])

    exclusion_text = ""
    if previous_topics:
        exclusion_text = "\nPREVIOUSLY COVERED TOPICS (DO NOT REPEAT THESE UNLESS THERE IS A MAJOR NEW UPDATE):\n" + "\n".join(previous_topics)

    prompt = f"""
You are an expert AI technology researcher for the 'Frontier Pulse' podcast.
Today is being researched for the weekly edition date: {edition_date}.

EXPLICIT COVERAGE WINDOW:
You MUST search for announcements published strictly within this window:
- START: {start_date}
- END: {end_date}
(Timezone is America/Bogota, UTC-5).

PRIORITY MONITORED PROJECTS:
You MUST specifically search for any new announcements, blog posts, model releases, or updates published within this coverage window regarding:
{priority_str}

SEARCH INSTRUCTIONS:
1. FIRST, execute search queries explicitly checking if there are any new updates published within the coverage window ({start_date} to {end_date}) for the Priority Monitored Projects (especially Project Astra, Gemini, Claude, Llama, OpenAI, NotebookLM).
2. SECOND, search for other major AI developments or open-source releases across top labs and publications.
3. Verify that all selected news items were published strictly within the coverage window ({start_date} to {end_date}).
4. Collect a WIDER candidate set: find at least 6 to 10 potential news stories.

EXCLUSION LIST:
{exclusion_text}

OUTPUT INSTRUCTIONS:
- Select 6 to 10 candidates from the coverage window, prioritizing any match from the Priority Monitored Projects list.
- CRITICAL MANDATORY RULE: Every single item in the 'items' list MUST have a 'sources' list containing at least one valid source with a title and a canonical URL (http/https). Do NOT omit the 'sources' field or leave it empty under any circumstance, as doing so will break the validation schema.
- Output your response STRICTLY as a raw valid JSON block inside ```json and ```.
- You MUST follow this exact schema format with the EXACT keys listed:

```json
{{
  "edition_date": "{edition_date}",
  "start_date": "{start_date}",
  "end_date": "{end_date}",
  "items": [
    {{
      "id": "lowercase-hyphenated-id",
      "title": "Clear descriptive title of the news",
      "category": "Category name (e.g., LLMs, Open Source, Agents)",
      "summary": "Detailed, factual 2-3 sentence summary of the breakthrough and why it matters.",
      "why_it_matters": "Detailed explanation of why this development is highly relevant to Jonathan's priority areas.",
      "key_takeaways": [
        "Key takeaway 1",
        "Key takeaway 2"
      ],
      "sources": [
        {{
          "title": "Title of the source page",
          "url": "https://canonical-url-of-source.com",
          "publisher": "Publisher or Organization Name",
          "published_date": "YYYY-MM-DD"
        }}
      ]
    }}
  ]
}}
```

Make sure 'items' is used as the key for candidates (do NOT use 'news_items'). Do not include any other markdown text outside the json block.
"""
    return prompt.strip()


def build_selection_prompt(candidates: list[dict], history_summaries: list[str], edition_date: str, start_date: str, end_date: str) -> str:
    """Build Selection Stage prompt, instructing Gemini to rank, score, and select top 3-4 news items."""
    candidates_str = json.dumps(candidates, ensure_ascii=False, indent=2)
    history_str = "\n".join(history_summaries) if history_summaries else "No recent history."

    prompt = f"""
You are the Chief Editorial Director of the 'Frontier Pulse' podcast.
We are finalizing the edition for date: {edition_date}.

EXPLICIT COVERAGE WINDOW:
The research coverage window for this edition is:
- START: {start_date}
- END: {end_date}
(Timezone is America/Bogota, UTC-5).

We have conducted dynamic web research and compiled the following list of candidate news stories:
---
CANDIDATE STORIES:
{candidates_str}
---

RECENTLY COVERED STORIES (PAST WEEKS):
{history_str}

YOUR TASK:
1. Review the candidate stories and compare them against recently covered stories to ensure NO duplicates or redundant announcements.
2. Select the top 3 to 4 best, most relevant stories for this edition ('{edition_date}').
3. For each selected story, you MUST rank and score them on:
   - Relevance Score (relevance_score: integer from 1 to 5): How aligned it is to Jonathan's priority topics.
   - Evidence Score (evidence_score: integer from 1 to 5): Strength of source URLs and official announcements.
4. Fill in the 'selection_reason' to justify why this story was chosen over other candidates.
5. Set 'is_slow_week' to true if there are fewer than 2 high-quality announcements, otherwise false.
6. Provide a professional, engaging 'title' for this edition, e.g., 'Frontier Pulse - Edición {edition_date}'.
7. Inject the explicit 'start_date' and 'end_date' into the respective schema fields.
8. Return the finalized edition conforming to the requested schema.
"""
    return prompt.strip()


def parse_json_from_response(text: str) -> dict:
    """Extract and parse JSON object from model response text."""
    cleaned = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Failed to parse JSON response from Gemini research output: {e}\nRaw output:\n{text}")


def deterministic_deduplicate(candidates: list[NewsItem], history_editions: list[dict]) -> list[NewsItem]:
    """Algorithm to deterministically deduplicate candidates against history by exact URL and title similarity."""
    def normalize_url(url: str) -> str:
        url = url.strip().lower()
        url = url.split("?")[0].split("#")[0]
        while url.endswith("/"):
            url = url[:-1]
        return url

    # Collect all canonical source URLs from history
    historical_urls = set()
    historical_titles = []
    for edition in history_editions:
        for item in edition.get("items", []):
            if "title" in item:
                historical_titles.append(item["title"])
            for src in item.get("sources", []):
                if "url" in src:
                    historical_urls.add(normalize_url(src["url"]))

    print(f"[*] Loaded {len(historical_urls)} historical source URLs and {len(historical_titles)} historical titles for deduplication.")

    def get_title_words(title: str) -> set[str]:
        cleaned = re.sub(r"[^\w\s]", "", title.lower())
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "of", "from", "is", "was", "are", "were", "de", "la", "el", "en", "y", "o"}
        return {w for w in cleaned.split() if w and w not in stop_words}

    def jaccard_similarity(title1: str, title2: str) -> float:
        words1 = get_title_words(title1)
        words2 = get_title_words(title2)
        if not words1 or not words2:
            return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)

    filtered_candidates = []
    for cand in candidates:
        is_duplicate = False

        # 1. URL Deduplication
        for src in cand.sources:
            norm_url = normalize_url(str(src.url))
            if norm_url in historical_urls:
                print(f"[!] Filtered candidate '{cand.title}' due to matching source URL: {norm_url}")
                is_duplicate = True
                break

        if is_duplicate:
            continue

        # 2. Title Similarity Deduplication
        for hist_title in historical_titles:
            sim = jaccard_similarity(cand.title, hist_title)
            if sim >= 0.5:  # High word overlap threshold
                print(f"[!] Filtered candidate '{cand.title}' due to high title similarity ({sim:.2f}) with historical title: '{hist_title}'")
                is_duplicate = True
                break

        if not is_duplicate:
            filtered_candidates.append(cand)

    return filtered_candidates


def research_ai_news(edition_date: str = None) -> dict:
    """Run Two-Stage AI web research: Discovery (grounded) -> Filter -> Selection & Ranking (structured output)."""
    # Default to current date if not provided
    if not edition_date:
        edition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Calculate coverage window (America/Bogota, UTC-5)
    start_date, end_date = calculate_edition_window(edition_date)
    print(f"[*] Research Coverage Window explicitly set to:")
    print(f"    Target Edition: {edition_date}")
    print(f"    Start (UTC-5):  {start_date}")
    print(f"    End (UTC-5):    {end_date}")

    # 1. Load extended recent history (last 4 editions)
    history_editions = load_recent_history_editions(limit=4)
    previous_topics = extract_previous_topics(history_editions[0] if history_editions else None)

    client = get_genai_client()

    # === STAGE 1: Discovery (with Search Grounding) ===
    discovery_prompt = build_discovery_prompt(previous_topics, edition_date, start_date, end_date)
    print("\n[*] STAGE 1: Performing priority-driven AI web research (Discovery)...")

    try:
        response_stage1 = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=discovery_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
            )
        )

        print("[*] Stage 1: Parsing and validating candidates pool against Pydantic schema...")
        candidates_dict = parse_json_from_response(response_stage1.text)
        
        # Inject explicit window dates before validation to comply with schema
        candidates_dict["edition_date"] = edition_date
        candidates_dict["start_date"] = start_date
        candidates_dict["end_date"] = end_date

        # Defensive Auto-Repair: Ensure every candidate item contains a valid 'sources' list
        if isinstance(candidates_dict.get("items"), list):
            for item in candidates_dict["items"]:
                if "sources" not in item or not isinstance(item["sources"], list) or len(item["sources"]) == 0:
                    item_id = item.get("id", "unknown-story")
                    print(f"[!] Warning: Candidate item '{item_id}' is missing a valid 'sources' list. Auto-injecting a search fallback source to ensure robust schema validation.")
                    item["sources"] = [
                        {
                            "title": "Google Search Grounding Fallback",
                            "url": f"https://www.google.com/search?q={item.get('title', 'AI News').replace(' ', '+')}",
                            "publisher": "System Fallback Grounding",
                            "published_date": edition_date
                        }
                    ]

        discovery_edition = DiscoveryEdition.model_validate(candidates_dict)
        candidates_data = json.loads(discovery_edition.model_dump_json())

    except ValidationError as ve:
        print(f"\n[!] DATA VALIDATION ERROR IN STAGE 1 DISCOVERY:")
        print(f"Gemini output did not conform to DiscoveryEdition schema. Details: {ve}")
        if 'response_stage1' in locals() and response_stage1.text:
            print(f"Raw response text:\n{response_stage1.text}")
        raise ValueError(f"Fallen validation in Stage 1 Discovery: {ve}")
    except Exception as e:
        print(f"\n[!] ERROR IN STAGE 1 DISCOVERY: {e}")
        raise e

    # Save candidates to get_edition_dir(edition_date) / "candidates.json" for auditing
    edition_dir = get_edition_dir(edition_date)
    candidates_file = edition_dir / "candidates.json"
    candidates_file_legacy = OUTPUT_DIR / f"candidates_{edition_date}.json"
    with open(candidates_file, "w", encoding="utf-8") as f:
        json.dump(candidates_data, f, ensure_ascii=False, indent=2)
    with open(candidates_file_legacy, "w", encoding="utf-8") as f:
        json.dump(candidates_data, f, ensure_ascii=False, indent=2)
    print(f"[+] Saved {len(candidates_data.get('items', []))} candidates to: {candidates_file}")

    # === INTERMEDIATE: Deterministic Deduplication ===
    print("\n[*] INTERMEDIATE: Performing deterministic deduplication against historical editions...")
    raw_candidates = [NewsItem.model_validate(item) for item in candidates_data.get("items", [])]
    deduplicated_candidates = deterministic_deduplicate(raw_candidates, history_editions)
    print(f"[+] Deduplication completed. Remaining candidates: {len(deduplicated_candidates)}")

    if not deduplicated_candidates:
        print("[!] Warning: All candidate stories were deduplicated. Reverting to raw candidates to avoid empty edition.")
        deduplicated_candidates = raw_candidates

    # Convert remaining candidates back to simple list of dicts
    dedup_candidates_dicts = [json.loads(c.model_dump_json()) for c in deduplicated_candidates]

    # === STAGE 2: Selection & Ranking (Structured Output) ===
    print("\n[*] STAGE 2: Performing editorial selection and scoring (Selection & Ranking)...")
    history_summaries = []
    for edition in history_editions:
        ed_date = edition.get("edition_date", "Unknown Date")
        for item in edition.get("items", []):
            history_summaries.append(f"- [{ed_date}] {item.get('title')}: {item.get('summary')}")

    selection_prompt = build_selection_prompt(dedup_candidates_dicts, history_summaries, edition_date, start_date, end_date)

    try:
        # Use native response_schema since we don't need Google Search Grounding in selection!
        response_stage2 = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=selection_prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=Edition,
            )
        )

        print("[*] Stage 2: Parsing and validating finalized selected edition...")
        edition_pydantic = Edition.model_validate_json(response_stage2.text)
        
        # Ensure start_date and end_date are guaranteed to be in the final news dict
        edition_pydantic.start_date = start_date
        edition_pydantic.end_date = end_date
        
        news_data = json.loads(edition_pydantic.model_dump_json())

    except ValidationError as ve:
        print(f"\n[!] DATA VALIDATION ERROR IN STAGE 2 SELECTION:")
        print(f"Gemini output did not conform to Edition schema. Details: {ve}")
        if 'response_stage2' in locals() and response_stage2.text:
            print(f"Raw response text:\n{response_stage2.text}")
        raise ValueError(f"Fallen validation in Stage 2 Selection: {ve}")
    except Exception as e:
        print(f"\n[!] ERROR IN STAGE 2 SELECTION: {e}")
        raise e

    # Save to input/current_news.json and get_edition_dir(edition_date) / "edition.json"
    edition_dir = get_edition_dir(edition_date)
    edition_file = edition_dir / "edition.json"
    INPUT_DIR.mkdir(exist_ok=True)
    current_news_path = INPUT_DIR / "current_news.json"
    
    with open(edition_file, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)
    with open(current_news_path, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)

    print(f"[+] Web research completed! Selected {len(news_data.get('items', []))} top-tier news items.")
    print(f"[+] Saved news dataset to: {edition_file}")

    # Save entry to history
    save_history_entry(news_data)

    return news_data


if __name__ == "__main__":
    research_ai_news()
