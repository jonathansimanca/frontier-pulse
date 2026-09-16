import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from google.genai import types
from pydantic import ValidationError

from src.config import (
    INPUT_DIR,
    OUTPUT_DIR,
    get_edition_dir,
    get_genai_client,
    get_current_edition_date,
    GEMINI_RESEARCH_MODEL,
    GEMINI_RESEARCH_FALLBACK_MODEL,
    MAX_API_RETRIES,
    RESEARCH_TRACKS,
    BLOCKED_DOMAINS,
    DEFAULT_TRACK_DISCOVERY_FOCUS,
    TRACK_DISCOVERY_FOCUS,
    MIN_CANDIDATES_PER_TRACK,
    MAX_CANDIDATES_PER_TRACK,
    MAX_DISCOVERY_POOL_SIZE,
    CLAIM_CHECK_ENABLED,
    LINK_CHECK_ENABLED,
    LINK_CHECK_TIMEOUT_SECONDS,
    LINK_CHECK_MAX_WORKERS,
)
from src.claim_verifier import verify_edition_claims
from src.editorial_priority import classify_candidates, enforce_priority_inclusion
from src.research_audit import AUDIT_FILENAME, ResearchAuditRecorder, extract_grounding_metadata
from src.source_link_checker import check_urls, network_unavailable, remove_broken_sources
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
    """Build focused Discovery Stage prompt for a specific research track.

    The track focus comes from ``TRACK_DISCOVERY_FOCUS`` so that each track searches
    for its own kind of development instead of inheriting a product-launch framing.
    """
    queries_str = "\n".join([f"- {q}" for q in queries])
    track_focus = TRACK_DISCOVERY_FOCUS.get(track_name, DEFAULT_TRACK_DISCOVERY_FOCUS)
    exclusion_text = ""
    if previous_topics:
        exclusion_text = "\nPREVIOUSLY COVERED TOPICS (DO NOT REPEAT UNLESS MAJOR BREAKING UPDATE):\n" + "\n".join(previous_topics[:6])

    prompt = f"""
You are an expert AI technology researcher for the 'Frontier Pulse' podcast.
We are discovering candidates for the research track: '{track_name.upper()}'.
Edition Date: {edition_date}
Coverage Window: {human_window} (strictly between {start_date} and {end_date}).

TRACK FOCUS:
{track_focus}.

TARGET SEARCH QUERIES TO INVESTIGATE:
{queries_str}

MANDATORY EDITORIAL INSTRUCTIONS:
1. Search actively for developments matching the TRACK FOCUS above that were published strictly within {human_window}.
2. ONLY include real, substantive developments. STRICTLY IGNORE:
   - Third-party weekly stock/investment portfolio trackers (e.g. CapitalBench).
   - Social media promotions for mobile/internet subscriptions or telecom deals.
   - Minor standards updates, predictions, or opinion pieces that do not report a concrete action, decision, or on-the-record statement.
   NOTE: On-the-record public statements, open letters, joint commitments, or policy decisions by frontier-lab leaders, leading researchers, governments, or recognized AI safety organizations are substantive developments, not speculation. Include them when they materially affect AI development.
3. Prioritize primary official sources (e.g., official lab blogs like blog.google, openai.com, anthropic.com, deepseek.com, x.ai; government or AI safety institute publications) and reputable tech journalism.
4. Extract {MIN_CANDIDATES_PER_TRACK} to {MAX_CANDIDATES_PER_TRACK} high-value candidate news stories for this track. If fewer qualifying developments exist in the window, return only the real ones; never invent stories.
{exclusion_text}

FACTUAL ACCURACY RULES:
- State only facts that the cited sources explicitly report. Do not infer, embellish, or generalize.
- Attribute a statement, endorsement, or commitment to a named person or organization ONLY when a cited source reports that exact person or organization making it. Never extend one leader's or lab's position to other leaders or labs.
- When a claim comes from a single non-official source, write it as reported (e.g. "according to Reuters").
- Never invent quotes, figures, dates, names, or URLs.

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
    end_date: str,
    priority_signals: list[dict] | None = None,
) -> str:
    """Build Selection Stage prompt instructing Gemini to apply the 4-Tier Editorial Rubric and select the top 3-4 stories.

    Args:
        priority_signals: Optional flagged ``PrioritySignal.to_dict()`` records from
            ``src.editorial_priority``. Flagged candidates are listed explicitly so the model
            evaluates them as Tier 1 multi-lab safety/governance developments.
    """
    candidates_str = json.dumps(candidates, ensure_ascii=False, indent=2)
    history_str = "\n".join(history_summaries) if history_summaries else "No recent history."

    flagged = [s for s in (priority_signals or []) if s.get("flagged")]
    if flagged:
        flagged_lines = "\n".join(
            f"- id='{s.get('candidate_id')}' | title='{s.get('title')}' | labs: {', '.join(s.get('labs', []))} | signals: {', '.join(s.get('signals', []))}"
            for s in flagged
        )
        priority_section = f"""
DETERMINISTIC PRIORITY SIGNALS:
The following candidates were flagged as multi-lab frontier AI safety/governance developments:
{flagged_lines}
Verify each flagged candidate against its sources and the coverage window. If it is verified, rank it TIER 1 and select it.
Reject a flagged candidate ONLY if it is unverified, outside the coverage window, or a duplicate of a recently covered story, and state that reason.
"""
    else:
        priority_section = ""

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
  * Coordinated safety commitments, joint statements, or capability restrictions by multiple frontier AI labs (e.g. Anthropic, OpenAI, xAI, Google DeepMind).
  * Credible warnings or actions by frontier-lab leaders, governments, or recognized AI safety organizations that materially affect the speed, safety, or oversight of advanced AI (e.g. calls to slow down, pause, or limit frontier AI development).
- TIER 2 (Relevance 4, Evidence 4-5) - HIGH PRIORITY:
  * Major open-weights model weights and benchmark releases (e.g. Llama, Qwen, Kimi).
  * Major developer tooling, APIs, and computer-use agent frameworks with verified benchmarks.
  * Major changes to frontier-model safety policies, risk or deployment thresholds, or evaluation requirements (including independent or external pre-deployment evaluations).
  * International coordination, regulatory action, or governance agreements with direct implications for frontier AI development (e.g. AI safety institute frameworks, EU AI Office enforcement).
  * Funding rounds, valuations, and commercial or infrastructure partnerships. These are AT MOST TIER 2 and never Tier 1.
- TIER 3 (Relevance 2-3, Evidence 2-3) - LOW PRIORITY:
  * Minor version patches, enterprise integrations without broad technical impact.
- TIER 4 (Relevance 1, Evidence 1) - STRICTLY REJECT:
  * Third-party automated benchmark portfolio trackers (e.g. CapitalBench).
  * Local telecom promotions or hardware reseller ads.
  * Unverified social media rumors.

RANKING RULES:
- A verified multi-lab frontier AI safety or governance development must never be ranked below a single-company product launch, funding round, or partnership.
- When Tier 1 candidates exist, do not fill the edition with Tier 2 funding or partnership stories in their place.
{priority_section}
YOUR EDITORIAL TASK:
1. Compare candidates against recently covered stories to eliminate duplicates or redundant updates. Also treat candidates in the pool that describe the same event (even with different titles, ids, or source URLs) as duplicates: select only the best-sourced version.
2. Select the top 3 to 4 best Tier-1 and Tier-2 stories for this edition ('{edition_date}').
3. For each selected story, assign:
   - relevance_score: integer from 1 to 5 (based on the rubric above).
   - evidence_score: integer from 1 to 5 (based on source credibility).
   - selection_reason: concise editorial rationale explaining why it was chosen over lower-tier candidates.
4. Set 'is_slow_week' to true ONLY if there are fewer than 2 genuine Tier 1/2 announcements across all labs.
5. Provide a professional, compelling 'title' for this edition in English, e.g.:
   'Frontier Pulse - Edition {edition_date}: Gemini 3.7 Flash, DeepMind Restructuring, and UltraFast Inference'
6. Ensure start_date and end_date are preserved.
7. Keep each selected story factually faithful to its candidate: do not add people, endorsements, commitments, figures, or dates that the candidate does not contain, and keep its attributions.
8. Return the finalized edition conforming to the requested schema.
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


def deterministic_deduplicate(
    candidates: list[NewsItem],
    history_editions: list[dict],
    rejections: list[dict] | None = None,
) -> list[NewsItem]:
    """Algorithm to deterministically deduplicate candidates against history by exact URL and title similarity.

    Args:
        rejections: Optional list that receives one ``{id, title, stage, reason}`` event per
            removed candidate (stages ``historical_url_match`` / ``historical_title_similarity``).
    """
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
                if rejections is not None:
                    rejections.append({
                        "id": cand.id,
                        "title": cand.title,
                        "stage": "historical_url_match",
                        "reason": f"Source URL already covered in a recent edition: {norm_url}",
                    })
                is_duplicate = True
                break

        if is_duplicate:
            continue

        # 2. Title Similarity Deduplication
        for hist_title in historical_titles:
            sim = jaccard_similarity(cand.title, hist_title)
            if sim >= 0.5:
                print(f"[!] Filtered candidate '{cand.title}' due to high title similarity ({sim:.2f}) with historical title: '{hist_title}'")
                if rejections is not None:
                    rejections.append({
                        "id": cand.id,
                        "title": cand.title,
                        "stage": "historical_title_similarity",
                        "reason": f"Title similarity {sim:.2f} >= 0.50 with recent edition title: '{hist_title}'",
                    })
                is_duplicate = True
                break

        if not is_duplicate:
            filtered_candidates.append(cand)

    return filtered_candidates


def filter_candidate_sources(candidates_dict: dict, edition_date: str, events: list[dict] | None = None) -> list[dict]:
    """Drop candidates without sources or whose sources all belong to blocked domains.

    Candidates without sources are rejected rather than given a fabricated fallback URL,
    because an invented link would pass the quality gate's evidence check.

    Args:
        edition_date: Kept for call compatibility; not used.
        events: Optional list that receives ``{id, title, stage, reason}`` events for dropped
            candidates (``missing_sources`` or ``blocked_domain_sources``).
    """
    valid_items = []
    items = candidates_dict.get("items", [])

    for item in items:
        sources = item.get("sources", [])
        if not sources or not isinstance(sources, list):
            print(f"[!] Dropped candidate '{item.get('title')}' because discovery returned no sources.")
            if events is not None:
                events.append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "stage": "missing_sources",
                    "reason": "Discovery returned no sources for this candidate.",
                })
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
            if events is not None:
                blocked = sorted({extract_domain(str(src.get("url", ""))) for src in sources})
                events.append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "stage": "blocked_domain_sources",
                    "reason": f"All sources belong to blocked domains: {', '.join(blocked)}",
                })

    return valid_items


def _summarize_validation_error(exc: ValidationError, limit: int = 3) -> str:
    """Return a compact, single-line description of the first Pydantic validation errors."""
    parts = []
    for err in exc.errors()[:limit]:
        location = ".".join(str(p) for p in err.get("loc", ())) or "item"
        parts.append(f"{location}: {err.get('msg', 'invalid value')}")
    return "; ".join(parts)


def build_candidate_pool(
    track_results: list[tuple[str, list[dict]]],
    max_pool_size: int = MAX_DISCOVERY_POOL_SIZE,
) -> tuple[list[dict], list[dict]]:
    """Merge per-track discovery results into a validated, bounded pool.

    See :func:`build_candidate_pool_with_tracks` for the algorithm. Returns
    ``(accepted_items, rejections)``.
    """
    accepted, _, rejections = build_candidate_pool_with_tracks(track_results, max_pool_size)
    return accepted, rejections


def build_candidate_pool_with_tracks(
    track_results: list[tuple[str, list[dict]]],
    max_pool_size: int = MAX_DISCOVERY_POOL_SIZE,
) -> tuple[list[dict], list[str], list[dict]]:
    """Merge per-track discovery results into a validated, bounded candidate pool.

    All steps are deterministic:
    1. Interleave tracks round-robin (each track's first candidate, then each track's
       second, ...) so the size cap never starves the tracks that run last.
    2. Validate every candidate individually against ``NewsItem``; one malformed item is
       rejected on its own instead of aborting the whole research stage.
    3. Drop in-pool duplicates by normalized title (first occurrence wins).
    4. Stop accepting once ``max_pool_size`` candidates are in the pool.

    Args:
        track_results: Ordered ``(track_key, items)`` pairs from the discovery stage.
        max_pool_size: Maximum number of accepted candidates.

    Returns:
        ``(accepted_items, accepted_tracks, rejections)`` where accepted items are
        JSON-compatible dicts normalized by ``NewsItem``, ``accepted_tracks[i]`` is the track
        that produced ``accepted_items[i]``, and each rejection is a dict with ``track``,
        ``id``, ``title``, ``stage`` and ``reason`` keys.
    """
    interleaved: list[tuple[str, dict]] = []
    longest_track = max((len(items) for _, items in track_results), default=0)
    for rank in range(longest_track):
        for track_key, items in track_results:
            if rank < len(items):
                interleaved.append((track_key, items[rank]))

    accepted: list[dict] = []
    accepted_tracks: list[str] = []
    rejections: list[dict] = []
    seen_titles: set[str] = set()

    for track_key, raw_item in interleaved:
        raw_title = raw_item.get("title") if isinstance(raw_item, dict) else None
        raw_id = raw_item.get("id") if isinstance(raw_item, dict) else None

        def reject(stage: str, reason: str) -> None:
            rejections.append({
                "track": track_key,
                "id": raw_id,
                "title": raw_title,
                "stage": stage,
                "reason": reason,
            })

        try:
            news_item = NewsItem.model_validate(raw_item)
        except ValidationError as exc:
            reject("schema_validation", _summarize_validation_error(exc))
            continue

        title_key = news_item.title.strip().lower()
        if title_key in seen_titles:
            reject("pool_duplicate_title", "Same title already accepted from an earlier track or rank.")
            continue

        if len(accepted) >= max_pool_size:
            reject("pool_size_cap", f"Discovery pool already holds the maximum of {max_pool_size} candidates.")
            continue

        seen_titles.add(title_key)
        accepted.append(news_item.model_dump(mode="json"))
        accepted_tracks.append(track_key)

    return accepted, accepted_tracks, rejections


def apply_priority_inclusion(news_data: dict, candidates: list[dict]) -> tuple[dict, dict]:
    """Apply the multi-lab safety/governance inclusion guard and re-validate the edition.

    Returns the (possibly extended) edition dict and the guard's audit record.
    """
    guarded_edition, record = enforce_priority_inclusion(news_data, candidates)
    for decision in record["decisions"]:
        print(f"[*] Priority guard: '{decision['title']}' -> {decision['action']}")

    if not record["included_ids"]:
        return news_data, record

    validated = Edition.model_validate(guarded_edition)
    print(f"[+] Priority guard added {len(record['included_ids'])} story(ies) omitted by model selection: {record['included_ids']}")
    return json.loads(validated.model_dump_json()), record


def apply_source_link_checks(
    news_data: dict,
    candidates: list[dict],
    priority_signals: list[dict],
    checker=None,
) -> tuple[dict, list[dict], dict]:
    """Verify source links of selected stories and flagged candidates.

    Broken links are removed. Selected stories left without a working link are dropped, and
    flagged candidates left without one are excluded from the priority guard. When every link
    fails at the network level, nothing is removed.

    Returns ``(edition, guard_candidates, link_record)``. The edition may temporarily contain no
    items; :func:`finalize_edition_after_link_checks` validates it after the priority guard.
    """
    record = {
        "status": "skipped",
        "duration_ms": 0,
        "results": [],
        "removed_urls": {},
        "dropped_story_ids": [],
        "excluded_candidate_ids": [],
        "slow_week_adjusted": False,
        "note": None,
    }
    if not LINK_CHECK_ENABLED:
        record["note"] = "Link check disabled by configuration."
        return news_data, candidates, record

    flagged_ids = {s.get("candidate_id") for s in priority_signals if s.get("flagged")}
    flagged_candidates = [c for c in candidates if c.get("id") in flagged_ids]
    urls = [
        str(src.get("url"))
        for item in list(news_data.get("items", [])) + flagged_candidates
        for src in item.get("sources", []) or []
        if src.get("url")
    ]

    started = time.monotonic()
    results = (checker or check_urls)(urls, timeout=LINK_CHECK_TIMEOUT_SECONDS, max_workers=LINK_CHECK_MAX_WORKERS)
    record["duration_ms"] = int((time.monotonic() - started) * 1000)
    record["results"] = list(results.values())

    if network_unavailable(results):
        record["status"] = "network_unavailable"
        record["note"] = "Every link failed at the network level; no links were removed."
        print(f"[!] Warning: {record['note']}")
        return news_data, candidates, record

    record["status"] = "success"
    kept_items, removed_items, dropped_ids = remove_broken_sources(news_data.get("items", []), results)
    kept_flagged, removed_flagged, excluded_ids = remove_broken_sources(flagged_candidates, results)
    record["removed_urls"] = {**removed_flagged, **removed_items}
    record["dropped_story_ids"] = dropped_ids
    record["excluded_candidate_ids"] = excluded_ids

    kept_flagged_by_id = {c.get("id"): c for c in kept_flagged}
    guard_candidates = [
        kept_flagged_by_id[c.get("id")] if c.get("id") in flagged_ids else c
        for c in candidates
        if c.get("id") not in flagged_ids or c.get("id") in kept_flagged_by_id
    ]

    counts = {status: sum(1 for r in results.values() if r["status"] == status) for status in ("reachable", "blocked", "broken", "unverified")}
    print(f"[+] Link check: {counts}. Removed broken links from {len(record['removed_urls'])} item(s); dropped stories: {dropped_ids}")

    edition = dict(news_data)
    edition["items"] = kept_items
    return edition, guard_candidates, record


def finalize_edition_after_link_checks(news_data: dict, link_record: dict) -> dict:
    """Validate the edition after link checks and the priority guard.

    Raises ``RuntimeError`` when no story with a working link remains. When link checks dropped
    stories and fewer than 3 remain, the edition is marked as a slow week so the quality gate
    accepts a shorter edition instead of padding it with weaker stories.
    """
    items = news_data.get("items", [])
    if not items:
        raise RuntimeError("No selected story has a working source link after link verification.")
    if link_record.get("dropped_story_ids") and len(items) < 3 and not news_data.get("is_slow_week"):
        news_data = dict(news_data, is_slow_week=True)
        link_record["slow_week_adjusted"] = True
        print(f"[*] Link check left {len(items)} stories; marking edition as a slow week.")
    return json.loads(Edition.model_validate(news_data).model_dump_json())


def research_ai_news(edition_date: str = None) -> dict:
    """Run Multi-Track AI web research: Discovery -> Deduplication -> 4-Tier Selection & Ranking.

    Every stage is recorded in ``output/editions/<date>/research_audit.json``. The audit is
    saved incrementally and marked ``failed`` if the research stage raises.
    """
    if not edition_date:
        edition_date = get_current_edition_date()

    start_date, end_date = calculate_edition_window(edition_date)
    audit = ResearchAuditRecorder(
        edition_date=edition_date,
        start_date=start_date,
        end_date=end_date,
        output_path=get_edition_dir(edition_date) / AUDIT_FILENAME,
        research_model=GEMINI_RESEARCH_MODEL,
        fallback_model=GEMINI_RESEARCH_FALLBACK_MODEL,
        max_pool_size=MAX_DISCOVERY_POOL_SIZE,
    )
    try:
        news_data = _run_research(edition_date, start_date, end_date, audit)
    except BaseException as exc:
        audit.mark_failed(exc)
        raise
    audit.mark_completed()
    print(f"[+] Research audit saved to: {audit.output_path}")
    return news_data


def _elapsed_ms(started_monotonic: float) -> int:
    return int((time.monotonic() - started_monotonic) * 1000)


def _run_research(edition_date: str, start_date: str, end_date: str, audit: ResearchAuditRecorder) -> dict:
    """Research stage body; see :func:`research_ai_news`."""
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
    track_results: list[tuple[str, list[dict]]] = []
    research_model = GEMINI_RESEARCH_MODEL

    # === STAGE 1: Multi-Track Discovery (with Search Grounding) ===
    print(f"\n[*] STAGE 1: Performing Multi-Track AI Web Research with {research_model}...")
    
    for track_key, track_queries in RESEARCH_TRACKS.items():
        print(f"    -> Investigating Research Track: '{track_key}' ({len(track_queries)} queries)...")
        track_prompt = build_track_discovery_prompt(
            track_key, track_queries, previous_topics, edition_date, human_window, start_date, end_date
        )
        audit.start_track(track_key, track_queries, track_prompt)

        track_success = False
        max_attempts = 3

        for attempt_idx in range(1, max_attempts + 1):
            curr_model = research_model if attempt_idx == 1 else GEMINI_RESEARCH_FALLBACK_MODEL
            temp = 0.3 if attempt_idx == 1 else 0.1
            attempt_started_at = datetime.now(timezone.utc)
            attempt_clock = time.monotonic()
            search_queries: list[str] = []
            grounding_sources: list = []
            try:
                track_response = client.models.generate_content(
                    model=curr_model,
                    contents=track_prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        temperature=temp,
                    )
                )
                search_queries, grounding_sources = extract_grounding_metadata(track_response)
                parsed_track = parse_json_from_response(track_response.text)
                raw_track_items = list(parsed_track.get("items", []))
                audit.record_track_candidates(track_key, raw_track_items)
                source_events: list[dict] = []
                track_items = filter_candidate_sources(parsed_track, edition_date, events=source_events)
                audit.record_track_attempt(
                    track_key, attempt_idx, curr_model, temp, attempt_started_at, _elapsed_ms(attempt_clock),
                    status="success", web_search_queries=search_queries, grounding_sources=grounding_sources,
                )
                audit.apply_candidate_events(track_key, source_events)
                prefix = f"({curr_model})" if curr_model != GEMINI_RESEARCH_MODEL else ""
                print(f"       [+] {prefix} Discovered {len(track_items)} candidates in track '{track_key}'")
                if len(track_items) < MIN_CANDIDATES_PER_TRACK:
                    print(f"       [!] Track '{track_key}' returned fewer than {MIN_CANDIDATES_PER_TRACK} candidates.")
                track_results.append((track_key, track_items))
                track_success = True
                # Safe pacing between track queries to protect Google Search Grounding RPM
                time.sleep(4)
                break
            except Exception as e:
                err_summary = str(e).split("\n")[0][:120]
                audit.record_track_candidates(track_key, [])
                audit.record_track_attempt(
                    track_key, attempt_idx, curr_model, temp, attempt_started_at, _elapsed_ms(attempt_clock),
                    status="error", error=f"{type(e).__name__}: {err_summary}",
                    web_search_queries=search_queries, grounding_sources=grounding_sources,
                )
                print(f"       [!] Track '{track_key}' attempt {attempt_idx}/{max_attempts} ({curr_model}) failed: {err_summary}")
                # Exponential backoff on rate limits / quota exhaustion / temporary spikes
                if any(err in err_summary for err in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                    sleep_time = 6 * attempt_idx
                    print(f"       [*] Rate limit or demand spike detected. Waiting {sleep_time}s before retry with fallback model...")
                    time.sleep(sleep_time)
                else:
                    time.sleep(3)

        audit.finish_track(track_key, "success" if track_success else "failed")
        if not track_success:
            print(f"       [!] Track '{track_key}' failed all {max_attempts} attempts. Skipping track.")

    # Build a validated, bounded pool (per-item validation, in-pool title dedup, fair cap)
    pool_items, pool_tracks, pool_rejections = build_candidate_pool_with_tracks(track_results, MAX_DISCOVERY_POOL_SIZE)
    for rejection in pool_rejections:
        print(
            f"[!] Rejected candidate '{rejection['title']}' from track '{rejection['track']}' "
            f"at {rejection['stage']}: {rejection['reason']}"
        )
    audit.record_pool(len(pool_items), pool_rejections)
    candidate_tracks = {(item.get("id"), item.get("title")): track for item, track in zip(pool_items, pool_tracks)}

    print(f"\n[*] Total candidates discovered across all tracks: {len(pool_items)}")
    if not pool_items:
        raise RuntimeError("Discovery stage produced no valid candidates across all research tracks.")

    # Validate candidates pool with DiscoveryEdition schema
    candidates_dict = {
        "edition_date": edition_date,
        "start_date": start_date,
        "end_date": end_date,
        "items": pool_items,
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
    dedup_rejections: list[dict] = []
    deduplicated_candidates = deterministic_deduplicate(raw_news_items, history_editions, rejections=dedup_rejections)
    print(f"[+] Deduplication completed. Remaining candidates: {len(deduplicated_candidates)}")

    reverted_to_raw = not deduplicated_candidates
    if reverted_to_raw:
        print("[!] Warning: All candidate stories were deduplicated. Reverting to raw candidates to avoid empty edition.")
        deduplicated_candidates = raw_news_items
    audit.record_deduplication(
        history_editions_loaded=len(history_editions),
        input_count=len(raw_news_items),
        rejections=dedup_rejections,
        candidate_tracks=candidate_tracks,
        reverted_to_raw=reverted_to_raw,
    )

    dedup_candidates_dicts = [json.loads(c.model_dump_json()) for c in deduplicated_candidates]

    # === STAGE 2: Selection & Ranking (Structured Output with Rubric) ===
    print("\n[*] STAGE 2: Performing editorial selection and scoring with 4-Tier Rubric...")
    history_summaries = []
    for edition in history_editions:
        ed_date = edition.get("edition_date", "Unknown Date")
        for item in edition.get("items", []):
            history_summaries.append(f"- [{ed_date}] {item.get('title')}: {item.get('summary')}")

    priority_signals = [signal.to_dict() for signal in classify_candidates(dedup_candidates_dicts)]
    for signal in priority_signals:
        if signal["flagged"]:
            print(f"[*] Priority signal: '{signal['title']}' flagged as {signal['category']}. {signal['reason']}")

    selection_prompt = build_selection_prompt(
        dedup_candidates_dicts, history_summaries, edition_date, start_date, end_date,
        priority_signals=priority_signals,
    )
    audit.start_selection(len(dedup_candidates_dicts), selection_prompt, priority_signals)

    selection_models = [research_model]
    if "gemini-3.7-flash" not in selection_models:
        selection_models.append("gemini-3.7-flash")
    selection_models = selection_models[:MAX_API_RETRIES]

    news_data = None
    for attempt_idx, sel_model in enumerate(selection_models, start=1):
        attempt_started_at = datetime.now(timezone.utc)
        attempt_clock = time.monotonic()
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
            audit.record_selection_attempt(
                attempt_idx, sel_model, 0.2, attempt_started_at, _elapsed_ms(attempt_clock), status="success"
            )
            break
        except Exception as e:
            err_summary = str(e).split("\n")[0][:120]
            audit.record_selection_attempt(
                attempt_idx, sel_model, 0.2, attempt_started_at, _elapsed_ms(attempt_clock),
                status="error", error=f"{type(e).__name__}: {err_summary}",
            )
            print(f"[!] Warning: Selection attempt {attempt_idx}/{len(selection_models)} with {sel_model} failed: {err_summary}")

    fallback_used = news_data is None
    if fallback_used:
        print("[!] Warning: All Stage 2 selection attempts failed. Constructing edition fallback directly from top candidate items.")
        selected_items = [dict(itm) for itm in dedup_candidates_dicts[:4]]
        for itm in selected_items:
            # Candidate dumps carry explicit None scores, so `or` (not a .get default) is required.
            itm["relevance_score"] = itm.get("relevance_score") or 4
            itm["evidence_score"] = itm.get("evidence_score") or 4
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

    model_selected_items = list(news_data.get("items", []))

    # === POST-SELECTION: Source link check (drops broken links and stories left without links) ===
    print("\n[*] LINK CHECK: Verifying source links of selected stories and flagged candidates...")
    news_data, guard_candidates, link_record = apply_source_link_checks(news_data, dedup_candidates_dicts, priority_signals)
    audit.record_link_check(link_record)

    # === POST-SELECTION: Deterministic priority inclusion guard ===
    news_data, priority_record = apply_priority_inclusion(news_data, guard_candidates)
    audit.annotate_priority_corroboration(priority_record, guard_candidates, candidate_tracks)
    news_data = finalize_edition_after_link_checks(news_data, link_record)
    audit.record_link_check(link_record)

    # === POST-SELECTION: Single grounded claim check (keeps original text on any failure) ===
    print("\n[*] CLAIM CHECK: Verifying factual claims of the selected stories...")
    news_data, claim_record = verify_edition_claims(client, news_data, research_model, enabled=CLAIM_CHECK_ENABLED)
    audit.record_claim_check(claim_record)
    audit.record_selection_result(
        model_selected_items=model_selected_items,
        final_items=news_data.get("items", []),
        priority_record=priority_record,
        fallback_used=fallback_used,
        candidate_tracks=candidate_tracks,
        candidates=dedup_candidates_dicts,
        link_dropped_ids=link_record["dropped_story_ids"],
    )

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
