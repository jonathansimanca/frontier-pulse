import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from google.genai import types

from src.config import (
    INPUT_DIR,
    OUTPUT_DIR,
    get_edition_dir,
    get_genai_client,
    get_current_edition_date,
    GEMINI_RESEARCH_MODEL,
    MAX_API_RETRIES,
    RESEARCH_TRACKS,
    BLOCKED_DOMAINS,
)
from src.schemas import Edition, DiscoveryEdition, NewsItem

# Directory for storing past weekly reports for deduplication
HISTORY_DIR = OUTPUT_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def extract_domain(url: str) -> str:
    """Extract clean domain name from URL."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


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


def calculate_edition_window(edition_date: str) -> tuple[str, str]:
    """Calculate the explicit 7-day research coverage window ending at the end of the target edition date.
    
    All times are computed relative to America/Bogota timezone (UTC-5).
    Example: For target edition date '2026-08-17', the window will cover:
      Start: 2026-08-10T00:00:00-05:00
      End:   2026-08-17T23:59:59-05:00
    """
    dt = datetime.strptime(edition_date, "%Y-%m-%d")
    start_dt = dt - timedelta(days=7)
    
    start_str = f"{start_dt.strftime('%Y-%m-%d')}T00:00:00-05:00"
    end_str = f"{dt.strftime('%Y-%m-%d')}T23:59:59-05:00"
    
    return start_str, end_str


def format_human_date_window(edition_date: str) -> str:
    """Format human-readable date window for natural search queries (e.g. 'August 10, 2026 to August 17, 2026')."""
    dt = datetime.strptime(edition_date, "%Y-%m-%d")
    start_dt = dt - timedelta(days=7)
    return f"{start_dt.strftime('%B %d, %Y')} to {dt.strftime('%B %d, %Y')}"


def build_track_discovery_prompt(
    track_name: str,
    queries: list[str],
    previous_topics: list[str],
    edition_date: str,
    human_window: str,
    start_date: str,
    end_date: str
) -> str:
    """Build focused Discovery Stage prompt for a specific research track."""
    queries_str = "\n".join([f"- {q}" for q in queries])
    exclusion_text = ""
    if previous_topics:
        exclusion_text = "\nPREVIOUSLY COVERED TOPICS (DO NOT REPEAT UNLESS MAJOR BREAKING UPDATE):\n" + "\n".join(previous_topics[:6])

    prompt = f"""
You are an expert AI technology researcher for the 'Frontier Pulse' podcast.
We are discovering candidates for the research track: '{track_name.upper()}'.
Edition Date: {edition_date}
Coverage Window: {human_window} (strictly between {start_date} and {end_date}).

TARGET SEARCH QUERIES TO INVESTIGATE:
{queries_str}

MANDATORY EDITORIAL INSTRUCTIONS:
1. Search actively for major official announcements, model releases, technical benchmarks, developer tooling, or key industry/infrastructure developments published strictly within {human_window}.
2. ONLY include real, substantive developments. STRICTLY IGNORE:
   - Third-party weekly stock/investment portfolio trackers (e.g. CapitalBench).
   - Social media promotions for mobile/internet subscriptions or telecom deals.
   - Minor standards updates or speculative blog posts.
3. Prioritize primary official announcements (e.g., official lab blogs like blog.google, openai.com, anthropic.com, deepseek.com) and reputable tech journalism.
4. Extract 3 to 6 high-value candidate news stories for this track.
{exclusion_text}

OUTPUT INSTRUCTIONS:
- CRITICAL MANDATORY RULE: Every single item in the 'items' list MUST have a 'sources' list containing at least one valid source with a title and a canonical URL (http/https). Do NOT omit the 'sources' field.
- Output your response STRICTLY as a raw valid JSON block inside ```json and ``` matching this schema:

```json
{{
  "edition_date": "{edition_date}",
  "start_date": "{start_date}",
  "end_date": "{end_date}",
  "items": [
    {{
      "id": "lowercase-hyphenated-id",
      "title": "Clear descriptive title of the news",
      "category": "Category name (e.g., LLMs, Open Source, Agents, Infrastructure)",
      "summary": "Detailed, factual 2-3 sentence summary of the breakthrough, technical details, pricing or benchmarks.",
      "why_it_matters": "Detailed explanation of why this development is significant to frontier AI technology.",
      "key_takeaways": [
        "Key takeaway 1",
        "Key takeaway 2"
      ],
      "sources": [
        {{
          "title": "Title of the source page",
          "url": "https://canonical-url-of-source.com",
          "publisher": "Publisher or Lab Name",
          "published_date": "YYYY-MM-DD"
        }}
      ]
    }}
  ]
}}
```
"""
    return prompt.strip()


def build_selection_prompt(
    candidates: list[dict],
    history_summaries: list[str],
    edition_date: str,
    start_date: str,
    end_date: str
) -> str:
    """Build Selection Stage prompt instructing Gemini to apply the 4-Tier Editorial Rubric and select the top 3-4 stories."""
    candidates_str = json.dumps(candidates, ensure_ascii=False, indent=2)
    history_str = "\n".join(history_summaries) if history_summaries else "No recent history."

    prompt = f"""
You are the Chief Editorial Director of the 'Frontier Pulse' podcast.
We are finalizing the weekly edition for date: {edition_date}.
Coverage Window: {start_date} to {end_date} (America/Bogota, UTC-5).

---
CANDIDATE STORIES POOL:
{candidates_str}
---

RECENTLY COVERED STORIES (PAST WEEKS):
{history_str}

EDITORIAL EVALUATION & SELECTION RUBRIC:
You MUST rank candidate stories using this 4-tier rubric:

- TIER 1 (Relevance 5, Evidence 4-5) - MUST SELECT:
  * Major foundation model releases / updates (e.g. Gemini 3.7 Flash, DeepSeek V4 Pro, GPT-5.x, Claude releases).
  * Game-changing infrastructure or latency breakthroughs (e.g. OpenAI UltraFast on Cerebras, custom AI chips).
  * High-impact leadership / organizational restructuring at frontier labs (e.g. DeepMind executive changes).
- TIER 2 (Relevance 4, Evidence 4-5) - HIGH PRIORITY:
  * Major open-weights model weights and benchmark releases (e.g. Llama, Qwen, Kimi).
  * Major developer tooling, APIs, and computer-use agent frameworks with verified benchmarks.
- TIER 3 (Relevance 2-3, Evidence 2-3) - LOW PRIORITY:
  * Minor version patches, enterprise integrations without broad technical impact.
- TIER 4 (Relevance 1, Evidence 1) - STRICTLY REJECT:
  * Third-party automated benchmark portfolio trackers (e.g. CapitalBench).
  * Local telecom promotions or hardware reseller ads.
  * Unverified social media rumors.

YOUR EDITORIAL TASK:
1. Compare candidates against recently covered stories to eliminate duplicates or redundant updates.
2. Select the top 3 to 4 best Tier-1 and Tier-2 stories for this edition ('{edition_date}').
3. For each selected story, assign:
   - relevance_score: integer from 1 to 5 (based on the rubric above).
   - evidence_score: integer from 1 to 5 (based on source credibility).
   - selection_reason: concise editorial rationale explaining why it was chosen over lower-tier candidates.
4. Set 'is_slow_week' to true ONLY if there are fewer than 2 genuine Tier 1/2 announcements across all labs.
5. Provide a professional, compelling 'title' for this edition in English, e.g.:
   'Frontier Pulse - Edition {edition_date}: Gemini 3.7 Flash, DeepMind Restructuring, and UltraFast Inference'
6. Ensure start_date and end_date are preserved.
7. Return the finalized edition conforming to the requested schema.
"""
    return prompt.strip()


def parse_json_from_response(text: str) -> dict:
    """Extract and parse JSON object from model response text with resilient repair."""
    if not text:
        raise ValueError("Empty response text from model.")

    # 1. Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Extract outer JSON object or array
    match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
    if match:
        snippet = match.group(0)
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            # Try cleaning trailing commas
            snippet_cleaned = re.sub(r",\s*([\]}])", r"\1", snippet)
            try:
                return json.loads(snippet_cleaned)
            except json.JSONDecodeError:
                pass

    # 3. Fallback: Extract individual item objects if array structure was truncated
    items_matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
    items = []
    for item_str in items_matches:
        try:
            item_cleaned = re.sub(r",\s*([\]}])", r"\1", item_str)
            item_obj = json.loads(item_cleaned)
            if isinstance(item_obj, dict) and ("title" in item_obj or "summary" in item_obj):
                items.append(item_obj)
        except Exception:
            continue
    if items:
        return {"items": items}

    raise ValueError(f"Failed to parse JSON response from Gemini research output. Snippet:\n{cleaned[:300]}")


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
                    historical_urls.add(normalize_url(str(src["url"])))

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
                print(f"[!] Filtered candidate '{cand.title}' due to matching historical source URL: {norm_url}")
                is_duplicate = True
                break

        if is_duplicate:
            continue

        # 2. Title Similarity Deduplication
        for hist_title in historical_titles:
            sim = jaccard_similarity(cand.title, hist_title)
            if sim >= 0.5:
                print(f"[!] Filtered candidate '{cand.title}' due to high title similarity ({sim:.2f}) with historical title: '{hist_title}'")
                is_duplicate = True
                break

        if not is_duplicate:
            filtered_candidates.append(cand)

    return filtered_candidates


def filter_candidate_sources(candidates_dict: dict, edition_date: str) -> list[dict]:
    """Filter out items that only have sources from blocked domains, and auto-repair missing sources."""
    valid_items = []
    items = candidates_dict.get("items", [])
    
    for item in items:
        sources = item.get("sources", [])
        if not sources or not isinstance(sources, list):
            item["sources"] = [
                {
                    "title": f"Official Announcement - {item.get('title', 'AI Update')}",
                    "url": f"https://www.google.com/search?q={item.get('title', 'AI News').replace(' ', '+')}",
                    "publisher": "Search Grounding Fallback",
                    "published_date": edition_date
                }
            ]
            valid_items.append(item)
            continue
            
        # Check if all sources are from blocked domains
        clean_sources = []
        for src in sources:
            url = str(src.get("url", ""))
            domain = extract_domain(url)
            if not any(b in domain for b in BLOCKED_DOMAINS):
                clean_sources.append(src)
                
        if clean_sources:
            item["sources"] = clean_sources
            valid_items.append(item)
        else:
            print(f"[!] Dropped candidate '{item.get('title')}' because all its sources belong to blocked domains.")

    return valid_items


def research_ai_news(edition_date: str = None) -> dict:
    """Run Multi-Track AI web research: Discovery -> Deduplication -> 4-Tier Selection & Ranking."""
    if not edition_date:
        edition_date = get_current_edition_date()

    start_date, end_date = calculate_edition_window(edition_date)
    human_window = format_human_date_window(edition_date)
    print(f"[*] Research Coverage Window set to:")
    print(f"    Target Edition: {edition_date}")
    print(f"    Human Window:   {human_window}")
    print(f"    Start (UTC-5):  {start_date}")
    print(f"    End (UTC-5):    {end_date}")

    # 1. Load extended recent history (last 4 editions)
    history_editions = load_recent_history_editions(limit=4)
    previous_topics = extract_previous_topics(history_editions[0] if history_editions else None)

    client = get_genai_client()
    raw_candidates_pool = []
    research_model = GEMINI_RESEARCH_MODEL

    # === STAGE 1: Multi-Track Discovery (with Search Grounding) ===
    print(f"\n[*] STAGE 1: Performing Multi-Track AI Web Research with {research_model}...")
    
    for track_key, track_queries in RESEARCH_TRACKS.items():
        print(f"    -> Investigating Research Track: '{track_key}' ({len(track_queries)} queries)...")
        track_prompt = build_track_discovery_prompt(
            track_key, track_queries, previous_topics, edition_date, human_window, start_date, end_date
        )

        track_success = False
        max_attempts = 3

        for attempt_idx in range(1, max_attempts + 1):
            curr_model = research_model if attempt_idx == 1 else "gemini-3.6-flash"
            temp = 0.3 if attempt_idx == 1 else 0.1
            try:
                track_response = client.models.generate_content(
                    model=curr_model,
                    contents=track_prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        temperature=temp,
                    )
                )
                parsed_track = parse_json_from_response(track_response.text)
                track_items = filter_candidate_sources(parsed_track, edition_date)
                prefix = f"({curr_model})" if curr_model != GEMINI_RESEARCH_MODEL else ""
                print(f"       [+] {prefix} Discovered {len(track_items)} candidates in track '{track_key}'")
                raw_candidates_pool.extend(track_items)
                track_success = True
                # Pacing between track queries to avoid Gemini API RPM exhaustion
                time.sleep(3)
                break
            except Exception as e:
                err_summary = str(e).split("\n")[0][:120]
                print(f"       [!] Track '{track_key}' attempt {attempt_idx}/{max_attempts} ({curr_model}) failed: {err_summary}")
                # Exponential backoff on rate limits / quota exhaustion
                if "429" in err_summary or "RESOURCE_EXHAUSTED" in err_summary:
                    sleep_time = 5 * attempt_idx
                    print(f"       [*] Rate limit hit. Waiting {sleep_time}s before retry with fallback model...")
                    time.sleep(sleep_time)
                else:
                    time.sleep(2)

        if not track_success:
            print(f"       [!] Track '{track_key}' failed all {max_attempts} attempts. Skipping track.")

    # Deduplicate within the raw pool itself by title
    seen_titles = set()
    unique_raw_candidates = []
    for item in raw_candidates_pool:
        title_key = item.get("title", "").strip().lower()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_raw_candidates.append(item)

    print(f"\n[*] Total candidates discovered across all tracks: {len(unique_raw_candidates)}")

    # Validate candidates pool with DiscoveryEdition schema
    candidates_dict = {
        "edition_date": edition_date,
        "start_date": start_date,
        "end_date": end_date,
        "items": unique_raw_candidates,
    }
    
    discovery_edition = DiscoveryEdition.model_validate(candidates_dict)
    candidates_data = json.loads(discovery_edition.model_dump_json())

    # Save candidates for auditing
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
    raw_news_items = [NewsItem.model_validate(item) for item in candidates_data.get("items", [])]
    deduplicated_candidates = deterministic_deduplicate(raw_news_items, history_editions)
    print(f"[+] Deduplication completed. Remaining candidates: {len(deduplicated_candidates)}")

    if not deduplicated_candidates:
        print("[!] Warning: All candidate stories were deduplicated. Reverting to raw candidates to avoid empty edition.")
        deduplicated_candidates = raw_news_items

    dedup_candidates_dicts = [json.loads(c.model_dump_json()) for c in deduplicated_candidates]

    # === STAGE 2: Selection & Ranking (Structured Output with Rubric) ===
    print("\n[*] STAGE 2: Performing editorial selection and scoring with 4-Tier Rubric...")
    history_summaries = []
    for edition in history_editions:
        ed_date = edition.get("edition_date", "Unknown Date")
        for item in edition.get("items", []):
            history_summaries.append(f"- [{ed_date}] {item.get('title')}: {item.get('summary')}")

    selection_prompt = build_selection_prompt(
        dedup_candidates_dicts, history_summaries, edition_date, start_date, end_date
    )

    selection_models = [research_model]
    if "gemini-3.7-flash" not in selection_models:
        selection_models.append("gemini-3.7-flash")
    selection_models = selection_models[:MAX_API_RETRIES]

    news_data = None
    for attempt_idx, sel_model in enumerate(selection_models, start=1):
        try:
            response_stage2 = client.models.generate_content(
                model=sel_model,
                contents=selection_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=Edition,
                )
            )
            print(f"[*] Stage 2 ({sel_model}): Parsing and validating finalized selected edition...")
            edition_pydantic = Edition.model_validate_json(response_stage2.text)
            edition_pydantic.start_date = start_date
            edition_pydantic.end_date = end_date
            news_data = json.loads(edition_pydantic.model_dump_json())
            break
        except Exception as e:
            err_summary = str(e).split("\n")[0][:120]
            print(f"[!] Warning: Selection attempt {attempt_idx}/{len(selection_models)} with {sel_model} failed: {err_summary}")

    if news_data is None:
        print("[!] Warning: All Stage 2 selection attempts failed. Constructing edition fallback directly from top candidate items.")
        selected_items = dedup_candidates_dicts[:4]
        for itm in selected_items:
            itm["relevance_score"] = itm.get("relevance_score", 4)
            itm["evidence_score"] = itm.get("evidence_score", 4)
            itm["selection_reason"] = "Automated fallback selection from top-ranked candidate pool."
        fallback_edition = {
            "edition_date": edition_date,
            "start_date": start_date,
            "end_date": end_date,
            "title": f"Frontier Pulse - Edition {edition_date}: Weekly AI Intelligence Briefing",
            "is_slow_week": len(selected_items) < 2,
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
            "items": selected_items,
        }
        edition_pydantic = Edition.model_validate(fallback_edition)
        news_data = json.loads(edition_pydantic.model_dump_json())

    # Save finalized edition
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
