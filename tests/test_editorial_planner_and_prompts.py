"""Unit tests for Editorial Planner, Scene Prompt Builder, and Tactile Textures."""

import pytest
from PIL import Image, ImageDraw
from src.editorial_planner import (
    plan_editorial_cards,
    build_fallback_plan,
    clamp_words,
    slugify,
    map_category_to_scene_mode,
)
from src.scene_prompt_builder import (
    build_scene_prompt,
    SAFE_ZONE_DIRECTIVES,
    MODE_DESCRIPTIONS,
    NEGATIVE_PROMPT_DIRECTIVE,
)
from src.tactile_texture import (
    apply_paper_grain,
    draw_terracotta_brush_stroke,
    draw_apricot_marker_underline,
    draw_sage_emphasis_mark,
)
from src.visual_theme import (
    MAX_WORDS_COVER_HEADLINE,
    MAX_WORDS_INSIGHT_HEADLINE,
    MAX_WORDS_KEY_FACT,
    MAX_WORDS_WHY_IT_MATTERS,
    MAX_WORDS_ROUNDUP_TITLE,
)


def test_clamp_words():
    """Verify strict word count clamping."""
    text = "one two three four five six seven eight nine ten eleven"
    assert len(clamp_words(text, 8).split()) == 8
    assert len(clamp_words(text, 5).split()) == 5
    assert clamp_words("", 5) == ""


def test_slugify():
    """Verify hyphenated lowercase slug generation."""
    assert slugify("OpenAI Astra & Reasoning Breakthroughs") == "openai-astra-reasoning"
    assert slugify("Special @#$ Characters!") == "special-characters"


def test_map_category_to_scene_mode():
    """Verify deterministic category to mode mapping."""
    assert map_category_to_scene_mode("Autonomous Agents") == "orchestrator"
    assert map_category_to_scene_mode("AI Safety & Security") == "alert"
    assert map_category_to_scene_mode("Hardware & Compute Infrastructure") == "builder"
    assert map_category_to_scene_mode("Reasoning Models") == "analyst"


def test_build_fallback_plan_with_multiple_items():
    """Verify 4-card fallback plan with multiple news items."""
    sample_news = {
        "title": "Frontier Pulse - Edición 2026-08-24",
        "items": [
            {
                "id": "item-1",
                "title": "OpenAI anuncia nuevo modelo Astra",
                "category": "Reasoning Models",
                "summary": "Resuelve problemas matemáticos y de código.",
                "why_it_matters": "Acelera desarrollo técnico.",
                "sources": [{"url": "https://openai.com"}]
            },
            {
                "id": "item-2",
                "title": "Agentes autónomos en producción",
                "category": "Autonomous Agents",
                "summary": "Nuevas herramientas para orquestar flujos.",
                "why_it_matters": "Optimiza operaciones de ingeniería.",
                "sources": [{"url": "https://example.com"}]
            },
            {
                "id": "item-3",
                "title": "Avance en chips de baja latencia",
                "category": "Hardware",
                "summary": "Reducción de consumo en centros de datos."
            }
        ]
    }

    plan = build_fallback_plan(sample_news, episode_number=4, language="es")

    assert "cover" in plan
    assert len(plan["cover"]["headline"].split()) <= MAX_WORDS_COVER_HEADLINE
    assert plan["cover"]["scene_mode"] in ["analyst", "alert", "orchestrator", "builder", "neutral"]

    assert "story_a" in plan
    assert len(plan["story_a"]["title"].split()) <= MAX_WORDS_INSIGHT_HEADLINE
    assert len(plan["story_a"]["key_fact"].split()) <= MAX_WORDS_KEY_FACT
    assert len(plan["story_a"]["why_it_matters"].split()) <= MAX_WORDS_WHY_IT_MATTERS
    assert plan["story_a"]["why_it_matters"].startswith("POR QUÉ IMPORTA:")
    assert plan["story_a"]["slug"] == "item-1"

    assert "story_b" in plan
    assert plan["story_b"]["is_fallback_context"] is False
    assert plan["story_b"]["scene_mode"] == "orchestrator"

    assert "roundup" in plan
    assert len(plan["roundup"]["remaining_titles"]) >= 1
    assert len(plan["roundup"]["remaining_titles"][0].split()) <= MAX_WORDS_ROUNDUP_TITLE


def test_build_fallback_plan_with_single_item():
    """Verify limited-data fallback when only 1 news item exists (Section 8.4)."""
    sample_news = {
        "title": "Frontier Pulse - Edición 2026-08-24",
        "items": [
            {
                "id": "only-item",
                "title": "Avance solitario de la semana",
                "category": "Reasoning Models",
                "summary": "Desarrollo importante.",
                "why_it_matters": "Relevancia directa."
            }
        ]
    }

    plan = build_fallback_plan(sample_news, episode_number=4, language="es")
    assert plan["story_b"]["is_fallback_context"] is True
    assert plan["story_b"]["slug"] == "contexto-edicion"
    assert len(plan["roundup"]["remaining_titles"]) == 3


def test_scene_prompt_builder_directives():
    """Verify scene prompt builder includes required negative directives and text safe zones."""
    prompt_cover = build_scene_prompt("cover", "analyst", "Deep reasoning architecture")
    assert "ABSOLUTELY NO readable text" in prompt_cover
    assert "Aspect ratio 4:5 vertical portrait" in prompt_cover
    assert "bottom 45%" in prompt_cover

    prompt_roundup = build_scene_prompt("roundup", "narrator")
    assert "left 60%" in prompt_roundup
    assert "microphone" in prompt_roundup


def test_tactile_texture_primitives():
    """Verify that tactile textures can be drawn onto PIL images without error."""
    img = Image.new("RGBA", (1080, 1350), (27, 23, 21, 255))
    draw = ImageDraw.Draw(img)

    # Draw brush stroke
    draw_terracotta_brush_stroke(draw, (100, 100), (400, 110), stroke_width=12)

    # Draw marker underline
    draw_apricot_marker_underline(draw, (100, 200, 300, 240))

    # Draw sage emphasis mark
    draw_sage_emphasis_mark(draw, (500, 300), radius=25, mark_type="circle")

    # Apply paper grain
    grained_img = apply_paper_grain(img, intensity=0.04)
    assert grained_img.size == (1080, 1350)
    assert grained_img.mode == "RGBA"
