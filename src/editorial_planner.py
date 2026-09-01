"""Editorial Planner for Frontier Pulse Visual Assets.

Produces structured, concise, and validated editorial copy, story selection,
narrative scene mode assignments, and limited-data fallbacks.
Adheres strictly to Section 8, Section 9.2, and Section 11 requirements.
"""

import json
import re
from typing import Any, Dict, List, Optional
from src.config import get_genai_client, GEMINI_DEFAULT_MODEL
from src.visual_theme import (
    MAX_WORDS_COVER_HEADLINE,
    MAX_WORDS_INSIGHT_HEADLINE,
    MAX_WORDS_KEY_FACT,
    MAX_WORDS_WHY_IT_MATTERS,
    MAX_WORDS_ROUNDUP_TITLE,
)


def clamp_words(text: str, max_words: int) -> str:
    """Ensure a string does not exceed max_words."""
    if not text:
        return ""
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words])


def slugify(text: str, max_words: int = 3) -> str:
    """Convert text into a clean URL-friendly hyphenated slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    words = text.strip().split()[:max_words]
    slug = "-".join(words)
    return slug or "news"


def map_category_to_scene_mode(category: Optional[str]) -> str:
    """Deterministically map a news category to a Pulse narrative mode."""
    if not category:
        return "analyst"
    cat = category.lower()
    if any(k in cat for k in ["agent", "autonomous", "automation", "workflow", "multi-agent"]):
        return "orchestrator"
    elif any(k in cat for k in ["security", "governance", "regulation", "breach", "policy", "safety", "risk"]):
        return "alert"
    elif any(k in cat for k in ["hardware", "infrastructure", "chip", "compute", "robotics", "open source", "launch", "tool"]):
        return "builder"
    elif any(k in cat for k in ["model", "reasoning", "benchmark", "research", "math", "multimodal"]):
        return "analyst"
    return "analyst"


def build_fallback_plan(news_data: dict, episode_number: int, language: str = "es") -> dict:
    """Build a deterministic, fully-populated 4-card editorial plan without LLM calls."""
    items = news_data.get("items", [])
    if not items:
        raise ValueError("Cannot formulate visual plan from empty news items.")

    primary_item = items[0]
    secondary_item = items[1] if len(items) > 1 else None
    remaining_items = items[2:] if len(items) > 2 else []

    # 1. Cover Card
    cover_headline = clamp_words(
        f"3 avances de IA clave esta semana" if language == "es" else "3 key AI developments this week",
        MAX_WORDS_COVER_HEADLINE
    )
    cover_mode = map_category_to_scene_mode(primary_item.get("category"))
    cover_subject = f"Pulse exploring developments in {primary_item.get('category', 'Artificial Intelligence')}"

    # 2. Story A
    title_a = clamp_words(primary_item.get("title", "Avance relevante en IA"), MAX_WORDS_INSIGHT_HEADLINE)
    fact_a = clamp_words(primary_item.get("summary", "Desarrollo verificado en inteligencia artificial."), MAX_WORDS_KEY_FACT)
    why_raw_a = primary_item.get("why_it_matters", "Relevancia directa para la arquitectura tecnológica.")
    why_prefix = "POR QUÉ IMPORTA:" if language == "es" else "WHY IT MATTERS:"
    if not why_raw_a.startswith(why_prefix):
        why_raw_a = f"{why_prefix} {why_raw_a}"
    why_a = clamp_words(why_raw_a, MAX_WORDS_WHY_IT_MATTERS)
    slug_a = slugify(primary_item.get("id", primary_item.get("title", "story-a")))

    source_a = "Frontier Pulse"
    if primary_item.get("sources") and len(primary_item["sources"]) > 0:
        source_a = str(primary_item["sources"][0].get("url", primary_item["sources"][0].get("publisher", "Frontier Pulse")))

    mode_a = map_category_to_scene_mode(primary_item.get("category"))

    # 3. Story B / Fallback Context
    if secondary_item:
        title_b = clamp_words(secondary_item.get("title", "Innovación destacada en IA"), MAX_WORDS_INSIGHT_HEADLINE)
        fact_b = clamp_words(secondary_item.get("summary", "Avance técnico verificado."), MAX_WORDS_KEY_FACT)
        why_raw_b = secondary_item.get("why_it_matters", "Impacto en productividad y desarrollo.")
        if not why_raw_b.startswith(why_prefix):
            why_raw_b = f"{why_prefix} {why_raw_b}"
        why_b = clamp_words(why_raw_b, MAX_WORDS_WHY_IT_MATTERS)
        slug_b = slugify(secondary_item.get("id", secondary_item.get("title", "story-b")))
        source_b = "Frontier Pulse"
        if secondary_item.get("sources") and len(secondary_item["sources"]) > 0:
            source_b = str(secondary_item["sources"][0].get("url", secondary_item["sources"][0].get("publisher", "Frontier Pulse")))
        mode_b = map_category_to_scene_mode(secondary_item.get("category"))
        story_b_data = {
            "slug": slug_b,
            "title": title_b,
            "key_fact": fact_b,
            "why_it_matters": why_b,
            "source_reference": source_b,
            "scene_mode": mode_b,
            "scene_subject": f"Technical situation regarding {secondary_item.get('category', 'AI')}",
            "is_fallback_context": False
        }
    else:
        # Limited-data fallback (Section 8.4)
        story_b_data = {
            "slug": "contexto-edicion",
            "title": "Contexto y perspectiva de la semana",
            "key_fact": "Análisis consolidado sobre la evolución y tendencias de frontera en IA.",
            "why_it_matters": f"{why_prefix} Permite anticipar patrones tecnológicos clave.",
            "source_reference": "Frontier Pulse",
            "scene_mode": "analyst",
            "scene_subject": "Pulse reviewing high-level technology intelligence landscape",
            "is_fallback_context": True
        }

    # 4. Roundup (AR-04)
    remaining_titles: List[str] = []
    for item in remaining_items[:3]:
        raw_title = item.get("title", "")
        if raw_title:
            remaining_titles.append(clamp_words(raw_title, MAX_WORDS_ROUNDUP_TITLE))

    if not remaining_titles:
        if language == "es":
            remaining_titles = [
                "Análisis a fondo y contexto estratégico",
                "Señales clave para ingeniería y producto",
                "Recomendaciones prácticas para el equipo"
            ]
        else:
            remaining_titles = [
                "In-depth analysis and strategic context",
                "Key signals for engineering and product",
                "Actionable takeaways for teams"
            ]

    plan = {
        "cover": {
            "headline": cover_headline,
            "scene_mode": cover_mode,
            "scene_subject": cover_subject
        },
        "story_a": {
            "slug": slug_a,
            "title": title_a,
            "key_fact": fact_a,
            "why_it_matters": why_a,
            "source_reference": source_a,
            "scene_mode": mode_a,
            "scene_subject": f"Pulse analyzing {primary_item.get('category', 'AI breakthrough')}"
        },
        "story_b": story_b_data,
        "roundup": {
            "remaining_titles": remaining_titles[:3],
            "scene_subject": "Pulse narrating the remaining weekly signals at a microphone"
        }
    }

    return plan


def plan_editorial_cards(
    news_data: dict,
    episode_number: int,
    duration_minutes: int = 4,
    language: str = "es"
) -> dict:
    """Formulate structured, validated editorial card copy using Gemini or deterministic fallback."""
    items = news_data.get("items", [])
    if not items:
        raise ValueError("Cannot plan visual cards from empty news items.")

    fallback = build_fallback_plan(news_data, episode_number, language)

    try:
        client = get_genai_client()
        prompt = f"""You are the Lead Visual Designer and Editor for Frontier Pulse, a premier AI technology watch podcast.
Formulate structured copy and narrative modes for exactly 4 mobile video visual cards (1080x1350 px, 4:5 aspect ratio) based on this week's news.

Edition Title: {news_data.get('title', '')}
Language: Latin American Spanish ({language})
Items:
{json.dumps([{
    'id': it.get('id'),
    'title': it.get('title'),
    'category': it.get('category'),
    'summary': it.get('summary'),
    'why_it_matters': it.get('why_it_matters'),
    'sources': it.get('sources', [])
} for it in items[:5]], indent=2, ensure_ascii=False)}

CONSTRAINTS & RULES:
1. ALL user-facing text MUST be in Latin American Spanish.
2. Cover Card (AR-01):
   - headline: EXACTLY 1 benefit-led headline. MAXIMUM 8 WORDS.
   - scene_mode: one of ["analyst", "alert", "orchestrator", "builder", "neutral"]
   - scene_subject: concise situation for background illustration (NO text).
3. Story A (AR-02, Primary News Item):
   - slug: 2-3 word lowercase hyphenated topic slug.
   - title: Plain-language headline. MAXIMUM 8 WORDS.
   - key_fact: 1 verifiable factual sentence describing what happened. MAXIMUM 20 WORDS.
   - why_it_matters: Short practical implication starting with "POR QUÉ IMPORTA: ". MAXIMUM 16 WORDS (including prefix).
   - source_reference: string url or publisher.
   - scene_mode: one of ["analyst", "alert", "orchestrator", "builder"]
   - scene_subject: concise visual situation.
4. Story B (AR-03, Secondary News Item):
   - slug, title (max 8 words), key_fact (max 20 words), why_it_matters (max 16 words, starting with "POR QUÉ IMPORTA: "), source_reference, scene_mode, scene_subject.
5. Roundup (AR-04, Closing Radar):
   - remaining_titles: array of up to 3 remaining story titles, each MAXIMUM 7 WORDS.
   - scene_subject: "Pulse narrating the remaining weekly signals at a microphone"

Respond strictly with valid JSON conforming to this schema:
{{
  "cover": {{
    "headline": "string (<= 8 words)",
    "scene_mode": "analyst | alert | orchestrator | builder | neutral",
    "scene_subject": "string"
  }},
  "story_a": {{
    "slug": "string",
    "title": "string (<= 8 words)",
    "key_fact": "string (<= 20 words)",
    "why_it_matters": "string (<= 16 words, starts with 'POR QUÉ IMPORTA: ')",
    "source_reference": "string",
    "scene_mode": "analyst | alert | orchestrator | builder",
    "scene_subject": "string"
  }},
  "story_b": {{
    "slug": "string",
    "title": "string (<= 8 words)",
    "key_fact": "string (<= 20 words)",
    "why_it_matters": "string (<= 16 words, starts with 'POR QUÉ IMPORTA: ')",
    "source_reference": "string",
    "scene_mode": "analyst | alert | orchestrator | builder",
    "scene_subject": "string"
  }},
  "roundup": {{
    "remaining_titles": ["string (<= 7 words)"],
    "scene_subject": "string"
  }}
}}
"""
        response = client.models.generate_content(
            model=GEMINI_DEFAULT_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        )

        data = json.loads(response.text)

        # Merge with strict bounds enforcement
        if "cover" in data and isinstance(data["cover"], dict):
            if data["cover"].get("headline"):
                fallback["cover"]["headline"] = clamp_words(data["cover"]["headline"], MAX_WORDS_COVER_HEADLINE)
            if data["cover"].get("scene_mode") in ["analyst", "alert", "orchestrator", "builder", "neutral"]:
                fallback["cover"]["scene_mode"] = data["cover"]["scene_mode"]
            if data["cover"].get("scene_subject"):
                fallback["cover"]["scene_subject"] = data["cover"]["scene_subject"]

        if "story_a" in data and isinstance(data["story_a"], dict):
            sa = data["story_a"]
            if sa.get("title"):
                fallback["story_a"]["title"] = clamp_words(sa["title"], MAX_WORDS_INSIGHT_HEADLINE)
            if sa.get("key_fact"):
                fallback["story_a"]["key_fact"] = clamp_words(sa["key_fact"], MAX_WORDS_KEY_FACT)
            if sa.get("why_it_matters"):
                why_val = sa["why_it_matters"].strip()
                if not why_val.startswith("POR QUÉ IMPORTA:"):
                    why_val = f"POR QUÉ IMPORTA: {why_val}"
                fallback["story_a"]["why_it_matters"] = clamp_words(why_val, MAX_WORDS_WHY_IT_MATTERS)
            if sa.get("slug"):
                fallback["story_a"]["slug"] = slugify(sa["slug"])
            if sa.get("scene_mode") in ["analyst", "alert", "orchestrator", "builder"]:
                fallback["story_a"]["scene_mode"] = sa["scene_mode"]
            if sa.get("scene_subject"):
                fallback["story_a"]["scene_subject"] = sa["scene_subject"]
            if sa.get("source_reference"):
                fallback["story_a"]["source_reference"] = sa["source_reference"]

        if "story_b" in data and isinstance(data["story_b"], dict) and len(items) > 1:
            sb = data["story_b"]
            if sb.get("title"):
                fallback["story_b"]["title"] = clamp_words(sb["title"], MAX_WORDS_INSIGHT_HEADLINE)
            if sb.get("key_fact"):
                fallback["story_b"]["key_fact"] = clamp_words(sb["key_fact"], MAX_WORDS_KEY_FACT)
            if sb.get("why_it_matters"):
                why_val = sb["why_it_matters"].strip()
                if not why_val.startswith("POR QUÉ IMPORTA:"):
                    why_val = f"POR QUÉ IMPORTA: {why_val}"
                fallback["story_b"]["why_it_matters"] = clamp_words(why_val, MAX_WORDS_WHY_IT_MATTERS)
            if sb.get("slug"):
                fallback["story_b"]["slug"] = slugify(sb["slug"])
            if sb.get("scene_mode") in ["analyst", "alert", "orchestrator", "builder"]:
                fallback["story_b"]["scene_mode"] = sb["scene_mode"]
            if sb.get("scene_subject"):
                fallback["story_b"]["scene_subject"] = sb["scene_subject"]
            if sb.get("source_reference"):
                fallback["story_b"]["source_reference"] = sb["source_reference"]
            fallback["story_b"]["is_fallback_context"] = False

        if "roundup" in data and isinstance(data["roundup"], dict):
            titles = data["roundup"].get("remaining_titles", [])
            if titles and isinstance(titles, list):
                clamped = [clamp_words(t, MAX_WORDS_ROUNDUP_TITLE) for t in titles[:3] if t]
                if clamped:
                    fallback["roundup"]["remaining_titles"] = clamped

    except Exception as e:
        print(f"[editorial_planner] Notice: Gemini card planning fallback used: {e}")

    return fallback
