import pytest
from PIL import Image
from src.schemas import CoverCardText, InsightCardText
from src.visual_asset_generator import (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    SAFE_MARGIN_X,
    SAFE_MARGIN_Y,
    get_font,
    wrap_text,
    create_base_gradient_background,
    render_cover_card,
    render_insight_card,
)


def test_canvas_dimensions_and_safe_margins():
    """Verify that canvas dimensions match the required 4:5 1080x1350 standard."""
    assert CANVAS_WIDTH == 1080
    assert CANVAS_HEIGHT == 1350
    assert SAFE_MARGIN_X >= 80
    assert SAFE_MARGIN_Y >= 80


def test_wrap_text():
    """Verify deterministic text wrapping within max pixel width."""
    from PIL import ImageDraw
    dummy_img = Image.new("RGBA", (100, 100))
    draw = ImageDraw.Draw(dummy_img)
    font = get_font(30)

    long_text = "This is a long sentence meant to test the deterministic text wrapping engine for Frontier Pulse."
    lines = wrap_text(long_text, font, max_width=400, draw=draw)

    assert len(lines) > 1
    # Check that reconstructed text contains all original words in order
    reconstructed = " ".join(lines)
    assert reconstructed == long_text


def test_render_cover_card_dimensions_and_mode():
    """Verify AR-01 Cover Card renders to 1080x1350 RGB image."""
    cover_data = CoverCardText(
        series="FRONTIER PULSE",
        format="PODCAST SEMANAL DE NOTICIAS DE IA",
        headline="3 avances de IA que debes entender esta semana",
        metadata="Episodio 4 · 4 min",
        cta="▶ Escuchar ahora"
    )

    img = render_cover_card(cover_data)
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_render_cover_card_with_background():
    """Verify AR-01 Cover Card composites cleanly over an existing background image."""
    bg_img = Image.new("RGB", (800, 1000), (40, 20, 60))
    cover_data = CoverCardText(
        series="FRONTIER PULSE",
        format="WEEKLY AI NEWS PODCAST",
        headline="Major AI breakthroughs shaping software engineering this week",
        metadata="Episode 4 · 5 min",
        cta="▶ Listen now"
    )

    img = render_cover_card(cover_data, background_image=bg_img)
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_render_insight_card_dimensions_and_mode():
    """Verify AR-02/AR-03 News Insight Card renders to 1080x1350 RGB image."""
    insight_data = InsightCardText(
        label="ESTA SEMANA EN IA",
        title="Los agentes empresariales se vuelven más autónomos",
        key_fact="OpenAI confirmó su modelo Astra capaz de resolver problemas matemáticos complejos.",
        why_it_matters="POR QUÉ IMPORTA: Acelera la automatización de flujos complejos en producción.",
        footer="FRONTIER PULSE · EPISODIO 4"
    )

    img = render_insight_card(insight_data)
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_slugify_and_clamp_words():
    """Verify slugify and word clamping helper functions."""
    from src.visual_asset_generator import slugify, clamp_words

    assert slugify("OpenAI Astra Math Breakthroughs") == "openai-astra-math"
    assert slugify("Special @#$ Characters!") == "special-characters"
    
    assert clamp_words("one two three four five", 3) == "one two three"
    assert clamp_words("short", 5) == "short"


def test_get_episode_number(monkeypatch):
    """Verify episode number resolution."""
    from src.visual_asset_generator import get_episode_number

    # Environment variable override
    monkeypatch.setenv("EPISODE_NUMBER", "42")
    assert get_episode_number() == 42
    monkeypatch.delenv("EPISODE_NUMBER")

    # Known dates
    assert get_episode_number("2026-08-05") == 1
    assert get_episode_number("2026-08-12") == 2
    assert get_episode_number("2026-08-18") == 3
    assert get_episode_number("2026-08-24") == 4


def test_plan_visual_card_contents_fallback(monkeypatch):
    """Verify fallback plan generation when Gemini API is not called or fails."""
    from src.visual_asset_generator import plan_visual_card_contents

    # Force Gemini to fail to test fallback mechanism
    def mock_failing_client():
        raise RuntimeError("Forced API client failure for fallback testing")

    monkeypatch.setattr("src.visual_asset_generator.get_genai_client", mock_failing_client)

    sample_news = {
        "title": "Frontier Pulse - Edición 2026-08-24",
        "items": [
            {
                "id": "openai-astra",
                "title": "OpenAI Confirms Astra Model and Breakthroughs",
                "category": "Reasoning Models",
                "summary": "OpenAI confirmed existence of Astra model solving 10 math problems.",
                "why_it_matters": "Astra pushes the boundary of autonomous reasoning.",
                "relevance_score": 5,
                "sources": [{"title": "OpenAI Blog", "url": "https://openai.com"}]
            },
            {
                "id": "anthropic-breach",
                "title": "Anthropic Discloses Claude Security Evaluation Results",
                "category": "AI Security",
                "summary": "Claude models breached real systems during security testing.",
                "why_it_matters": "Shows urgent need for sandboxing.",
                "relevance_score": 5,
                "sources": [{"title": "Anthropic Post", "url": "https://anthropic.com"}]
            }
        ]
    }

    plan = plan_visual_card_contents(sample_news, episode_number=4, language="es")
    assert "cover" in plan
    assert "story_a" in plan
    assert plan["story_a"]["slug"] == "openai-astra"
    assert plan["story_a"]["why_it_matters"].startswith("POR QUÉ IMPORTA:")
    assert plan["include_card_b"] is True
    assert plan["story_b"]["slug"] == "anthropic-breach"


def test_generate_visual_assets_end_to_end(tmp_path, monkeypatch):
    """Verify end-to-end asset generation writing PNGs and assets.json."""
    from src.visual_asset_generator import generate_visual_assets
    import json

    monkeypatch.setattr("src.visual_asset_generator.get_edition_dir", lambda date: tmp_path)
    # Mock background generation to avoid external network calls
    monkeypatch.setattr("src.visual_asset_generator.generate_background_artwork", lambda prompt: None)
    # Force deterministic fallback planning for unit test stability
    monkeypatch.setattr("src.visual_asset_generator.get_genai_client", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    sample_news = {
        "title": "Frontier Pulse - Edición 2026-08-24",
        "items": [
            {
                "id": "primary-topic",
                "title": "Primary breakthrough in AI models",
                "category": "Core AI",
                "summary": "Major release of multi-agent capabilities.",
                "why_it_matters": "Speeds up software development.",
                "relevance_score": 5,
                "sources": [{"title": "Source 1", "url": "https://example.com"}]
            }
        ]
    }

    manifest, file_paths = generate_visual_assets(
        news_data=sample_news,
        edition_date="2026-08-24",
        episode_number=4,
        audio_duration_minutes=4,
        language="es"
    )

    # Verify manifest
    assert manifest.episode_number == 4
    assert len(manifest.assets) >= 2

    # Verify files on disk
    cover_file = tmp_path / "episode-4-01-cover.png"
    assert cover_file.exists()
    cover_img = Image.open(cover_file)
    assert cover_img.size == (1080, 1350)

    insight_a_file = tmp_path / "episode-4-02-insight-primary-topic.png"
    assert insight_a_file.exists()
    insight_img = Image.open(insight_a_file)
    assert insight_img.size == (1080, 1350)

    manifest_file = tmp_path / "episode-4-assets.json"
    assert manifest_file.exists()
    with open(manifest_file, "r", encoding="utf-8") as f:
        loaded_json = json.load(f)
        assert loaded_json["episode_number"] == 4
        assert len(loaded_json["assets"]) >= 2
