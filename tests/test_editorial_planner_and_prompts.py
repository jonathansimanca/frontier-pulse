"""Unit tests for Editorial Planner, Scene Prompt Builder, Tactile Textures, and Language Consistency."""

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
    NEGATIVE_PROMPT_DIRECTIVE,
    MODE_COMPOSITION_DIRECTIVES,
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


def test_build_fallback_plan_with_multiple_items_spanish():
    """Verify 4-card fallback plan in Spanish with multiple news items."""
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
    assert "Pulse" not in plan["cover"]["scene_subject"]

    assert "story_a" in plan
    assert len(plan["story_a"]["title"].split()) <= MAX_WORDS_INSIGHT_HEADLINE
    assert len(plan["story_a"]["key_fact"].split()) <= MAX_WORDS_KEY_FACT
    assert len(plan["story_a"]["why_it_matters"].split()) <= MAX_WORDS_WHY_IT_MATTERS
    assert plan["story_a"]["why_it_matters"].startswith("POR QUÉ IMPORTA:")
    assert plan["story_a"]["slug"] == "item-1"
    assert "Pulse" not in plan["story_a"]["scene_subject"]

    assert "story_b" in plan
    assert plan["story_b"]["is_fallback_context"] is False
    assert plan["story_b"]["scene_mode"] == "orchestrator"
    assert "Pulse" not in plan["story_b"]["scene_subject"]

    assert "roundup" in plan
    assert len(plan["roundup"]["remaining_titles"]) >= 1
    assert len(plan["roundup"]["remaining_titles"][0].split()) <= MAX_WORDS_ROUNDUP_TITLE
    assert "Pulse" not in plan["roundup"]["scene_subject"]


def test_build_fallback_plan_english():
    """Verify 4-card fallback plan in English uses WHY IT MATTERS: and English defaults."""
    sample_news = {
        "title": "Frontier Pulse - Edition 2026-08-24",
        "items": [
            {
                "id": "item-1",
                "title": "OpenAI announces new Astra model",
                "category": "Reasoning Models",
                "summary": "Solves complex math and coding benchmarks.",
                "why_it_matters": "Accelerates technical capability.",
                "sources": [{"url": "https://openai.com"}]
            }
        ]
    }

    plan = build_fallback_plan(sample_news, episode_number=4, language="en")
    assert plan["story_a"]["why_it_matters"].startswith("WHY IT MATTERS:")
    assert plan["story_b"]["is_fallback_context"] is True
    assert plan["story_b"]["why_it_matters"].startswith("WHY IT MATTERS:")
    assert plan["story_b"]["slug"] == "edition-context"


def test_scene_prompt_builder_no_pulse_character_in_positive_prompt():
    """Verify that NO scene prompt contains the word 'Pulse' in the positive prompt,
    and all prompts contain text-safe zones and character exclusions."""
    modes = ["analyst", "alert", "orchestrator", "builder", "narrator", "neutral"]
    asset_types = ["cover", "insight", "roundup"]

    for a_type in asset_types:
        for mode in modes:
            prompt = build_scene_prompt(
                asset_type=a_type,
                scene_mode=mode,
                scene_subject="Pulse exploring distributed reasoning systems"
            )

            # 1. Negative exclusion checks
            assert "NO people" in prompt
            assert "NO human figures" in prompt
            assert "NO robots" in prompt
            assert "NO faces" in prompt
            assert "NO characters" in prompt
            assert "ABSOLUTELY NO readable text" in prompt

            # 2. Composition / Safe-zone checks
            assert "separately composited editorial character" in prompt
            assert "Aspect ratio 4:5 vertical portrait" in prompt
            if a_type == "cover":
                assert "bottom 45%" in prompt
            elif a_type == "insight":
                assert "bottom 55%" in prompt
            elif a_type == "roundup":
                assert "left 60%" in prompt

            # 3. Positive prompt must NOT include the word "Pulse"
            positive_part = prompt.split("ABSOLUTELY NO")[0]
            assert "Pulse" not in positive_part, f"Found 'Pulse' in positive prompt: {positive_part}"


def test_tactile_texture_primitives():
    """Verify that tactile textures can be drawn onto PIL images without error."""
    img = Image.new("RGBA", (1080, 1350), (27, 23, 21, 255))
    draw = ImageDraw.Draw(img)

    draw_terracotta_brush_stroke(draw, (100, 100), (400, 110), stroke_width=12)
    draw_apricot_marker_underline(draw, (100, 200, 300, 240))
    draw_sage_emphasis_mark(draw, (500, 300), radius=25, mark_type="circle")

    grained_img = apply_paper_grain(img, intensity=0.04)
    assert grained_img.size == (1080, 1350)
    assert grained_img.mode == "RGBA"
