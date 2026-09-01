"""Unit tests for Visual Asset Generator (4-Card Editorial Earth Tactile System)."""

import pytest
import json
from PIL import Image
from src.schemas import (
    CoverCardText,
    InsightCardText,
    EditionContextCardText,
    RoundupCardText,
    VisualAssetManifest,
)
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
    render_context_card,
    render_roundup_card,
    generate_visual_assets,
    get_episode_number,
    slugify,
    clamp_words,
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
    reconstructed = " ".join(lines)
    assert reconstructed == long_text


def test_render_cover_card_dimensions_and_mode():
    """Verify AR-01 Cover Card renders to 1080x1350 RGB image."""
    cover_data = CoverCardText(
        series="FRONTIER PULSE",
        format="PODCAST SEMANAL DE IA",
        headline="3 avances de IA clave esta semana",
        metadata="Episodio 4 · 4 min",
        cta="▶ Escuchar ahora"
    )

    img = render_cover_card(cover_data, scene_mode="analyst")
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_render_cover_card_with_background():
    """Verify AR-01 Cover Card composites cleanly over an existing background image."""
    bg_img = Image.new("RGB", (800, 1000), (40, 20, 60))
    cover_data = CoverCardText(
        series="FRONTIER PULSE",
        format="PODCAST SEMANAL DE IA",
        headline="Avances de IA de alto impacto",
        metadata="Episodio 4 · 5 min",
        cta="▶ Escuchar ahora"
    )

    img = render_cover_card(cover_data, background_image=bg_img, scene_mode="builder")
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_render_insight_card_dimensions_and_mode_spanish():
    """Verify AR-02/AR-03 News Insight Card renders on controlled reading surface in Spanish."""
    insight_data = InsightCardText(
        label="ESTA SEMANA EN IA",
        title="Los agentes empresariales se vuelven más autónomos",
        key_fact="OpenAI confirmó su modelo Astra capaz de resolver problemas matemáticos complejos.",
        why_it_matters="POR QUÉ IMPORTA: Acelera la automatización de flujos complejos en producción.",
        footer="FRONTIER PULSE · EPISODIO 4"
    )

    img = render_insight_card(insight_data, scene_mode="orchestrator")
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_render_insight_card_english():
    """Verify AR-02/AR-03 News Insight Card renders with English prefix WHY IT MATTERS:."""
    insight_data = InsightCardText(
        label="THIS WEEK IN AI",
        title="Autonomous agents deployed at scale in enterprise",
        key_fact="Anthropic rolled out major enhancements to Claude Developer Platform.",
        why_it_matters="WHY IT MATTERS: Pushes the frontier of agentic AI engineering workflows.",
        footer="FRONTIER PULSE · EPISODE 4"
    )

    img = render_insight_card(insight_data, scene_mode="builder")
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_render_context_card_fallback():
    """Verify AR-03 Fallback Context Card renders cleanly to 1080x1350 RGB image."""
    ctx_data = EditionContextCardText(
        label="CONTEXTO DE LA EDICIÓN",
        title="Panorama y contexto estratégico semanal",
        context_text="Análisis integral de señales y avances en la frontera de inteligencia artificial.",
        cta="▶ Escucha el episodio completo",
        footer="FRONTIER PULSE · EPISODIO 4"
    )
    img = render_context_card(ctx_data, scene_mode="analyst")
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_render_roundup_card_dimensions_and_mode():
    """Verify AR-04 Closing Radar Card renders to 1080x1350 RGB image."""
    roundup_data = RoundupCardText(
        label="RADAR DE CIERRE",
        headline="Más señales que debes tener en el radar",
        remaining_titles=[
            "Avances en chips neuronales",
            "Nuevas regulaciones de seguridad",
            "Alianza de robótica abierta"
        ],
        cta="Escucha el episodio completo",
        footer="FRONTIER PULSE · EPISODIO 4"
    )

    img = render_roundup_card(roundup_data)
    assert img.size == (1080, 1350)
    assert img.mode == "RGB"


def test_slugify_and_clamp_words():
    """Verify slugify and word clamping helper functions."""
    assert slugify("OpenAI Astra Math Breakthroughs") == "openai-astra-math"
    assert slugify("Special @#$ Characters!") == "special-characters"
    
    assert clamp_words("one two three four five", 3) == "one two three"
    assert clamp_words("short", 5) == "short"


def test_get_episode_number(monkeypatch):
    """Verify episode number resolution."""
    monkeypatch.setenv("EPISODE_NUMBER", "42")
    assert get_episode_number() == 42
    monkeypatch.delenv("EPISODE_NUMBER")

    assert get_episode_number("2026-08-05") == 1
    assert get_episode_number("2026-08-12") == 2
    assert get_episode_number("2026-08-18") == 3
    assert get_episode_number("2026-08-24") == 4


def test_generate_visual_assets_end_to_end(tmp_path, monkeypatch):
    """Verify end-to-end asset generation writing exactly 4 PNGs, JPEG, and assets.json."""
    monkeypatch.setattr("src.visual_asset_generator.get_edition_dir", lambda date: tmp_path)
    monkeypatch.setattr("src.visual_asset_generator.OUTPUT_DIR", tmp_path)
    # Mock background generation to avoid external network calls during tests
    monkeypatch.setattr("src.visual_asset_generator.generate_background_artwork", lambda prompt: None)
    # Force deterministic fallback planning for unit test offline stability
    monkeypatch.setattr("src.editorial_planner.get_genai_client", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    sample_news = {
        "title": "Frontier Pulse - Edición 2026-08-24",
        "items": [
            {
                "id": "primary-topic",
                "title": "Avance primario en modelos de razonamiento",
                "category": "Reasoning Models",
                "summary": "Lanzamiento de capacidades avanzadas de inferencia.",
                "why_it_matters": "Acelera desarrollo de software.",
                "relevance_score": 5,
                "sources": [{"title": "Source 1", "url": "https://example.com"}]
            },
            {
                "id": "secondary-topic",
                "title": "Nuevos agentes empresariales en producción",
                "category": "Autonomous Agents",
                "summary": "Herramientas para despliegue de multi-agentes.",
                "why_it_matters": "Automatiza flujos críticos.",
                "relevance_score": 4,
                "sources": [{"title": "Source 2", "url": "https://example.com/2"}]
            },
            {
                "id": "tertiary-topic",
                "title": "Chips de baja latencia para inferencia local",
                "category": "Hardware",
                "summary": "Reducción de consumo en centros de datos."
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

    # Verify manifest has exactly 4 assets
    assert manifest.episode_number == 4
    assert len(manifest.assets) == 4
    assert manifest.assets[0].type == "cover"
    assert manifest.assets[1].type == "news_insight"
    assert manifest.assets[2].type == "news_insight"
    assert manifest.assets[3].type == "news_roundup"

    # Verify files on disk
    cover_file = tmp_path / "episode-4-01-cover.png"
    assert cover_file.exists()
    assert Image.open(cover_file).size == (1080, 1350)

    insight_a_file = tmp_path / "episode-4-02-insight-primary-topic.png"
    assert insight_a_file.exists()
    assert Image.open(insight_a_file).size == (1080, 1350)

    insight_b_file = tmp_path / "episode-4-03-insight-secondary-topic.png"
    assert insight_b_file.exists()
    assert Image.open(insight_b_file).size == (1080, 1350)

    roundup_file = tmp_path / "episode-4-04-news-roundup.png"
    assert roundup_file.exists()
    assert Image.open(roundup_file).size == (1080, 1350)

    # Legacy cover compatibility
    jpg_file = tmp_path / "podcast_cover.jpg"
    assert jpg_file.exists()

    # Manifest file
    manifest_file = tmp_path / "episode-4-assets.json"
    assert manifest_file.exists()
    with open(manifest_file, "r", encoding="utf-8") as f:
        loaded_json = json.load(f)
        assert loaded_json["episode_number"] == 4
        assert len(loaded_json["assets"]) == 4


def test_english_single_story_edition_context_card_has_no_spanish(tmp_path, monkeypatch):
    """Verify that an English single-story edition generates an AR-03 context card with NO Spanish text."""
    monkeypatch.setattr("src.visual_asset_generator.get_edition_dir", lambda date: tmp_path)
    monkeypatch.setattr("src.visual_asset_generator.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("src.visual_asset_generator.generate_background_artwork", lambda prompt: None)
    monkeypatch.setattr("src.editorial_planner.get_genai_client", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    single_story_news = {
        "title": "Frontier Pulse - Edition 2026-08-24",
        "items": [
            {
                "id": "single-breakthrough",
                "title": "Major Breakthrough in Autonomous AI Systems",
                "category": "Autonomous Agents",
                "summary": "Engineering teams deploy scalable agentic architectures.",
                "why_it_matters": "Dramatically improves reliability in automated pipelines.",
                "relevance_score": 5,
                "sources": [{"title": "Source 1", "url": "https://example.com"}]
            }
        ]
    }

    manifest, file_paths = generate_visual_assets(
        news_data=single_story_news,
        edition_date="2026-08-24",
        episode_number=4,
        audio_duration_minutes=4,
        language="en"
    )

    assert len(manifest.assets) == 4
    context_card_asset = manifest.assets[2]
    assert context_card_asset.type == "edition_context"

    # Verify context text model fields contain NO Spanish words
    spanish_indicators = ["POR QUÉ IMPORTA", "EDICIÓN", "EPISODIO", "ESCUCHAR", "SEMANAL", "HECHO CLAVE"]
    text_data = context_card_asset.text

    assert "EDITION CONTEXT" in text_data.label
    assert "EPISODE 4" in text_data.footer
    assert "Listen" in text_data.cta

    for spanish_word in spanish_indicators:
        assert spanish_word not in text_data.label
        assert spanish_word not in text_data.title
        assert spanish_word not in text_data.context_text
        assert spanish_word not in text_data.cta
        assert spanish_word not in text_data.footer

    # Also directly verify render_context_card with language="en"
    rendered_img = render_context_card(text_data, language="en")
    assert rendered_img.size == (1080, 1350)


def test_renderers_enforce_contrast_validation_and_reject_invalid_colors():
    """Verify that every renderer preflights color pairs and raises ValueError on invalid contrast."""
    cover_data = CoverCardText(
        series="FRONTIER PULSE",
        format="WEEKLY AI PODCAST",
        headline="Valid Headline",
        metadata="Episode 4 · 4 min",
        cta="▶ Listen now"
    )

    # 1. Cover card with invalid low-contrast headline (dark gray text on dark surface)
    with pytest.raises(ValueError, match="Contrast validation failed for 'cover_headline'"):
        render_cover_card(cover_data, color_overrides={"headline_fg": (38, 34, 30)})

    # 2. Cover card with invalid low-contrast CTA text
    with pytest.raises(ValueError, match="Contrast validation failed for 'cover_cta'"):
        render_cover_card(cover_data, color_overrides={"cta_fg": (195, 75, 45)})

    # 3. Insight card with invalid low-contrast key fact body text
    insight_data = InsightCardText(
        label="THIS WEEK IN AI",
        title="Autonomous Systems at Scale",
        key_fact="Key fact text here.",
        why_it_matters="WHY IT MATTERS: High impact significance.",
        footer="FRONTIER PULSE · EPISODE 4"
    )
    with pytest.raises(ValueError, match="Contrast validation failed for 'insight_key_fact_body'"):
        render_insight_card(insight_data, color_overrides={"key_fact_body_fg": (40, 36, 32)})

    # 4. Insight card with invalid low-contrast label badge
    with pytest.raises(ValueError, match="Contrast validation failed for 'insight_label'"):
        render_insight_card(insight_data, color_overrides={"label_fg": (120, 140, 120)})

    # 5. Roundup card with invalid low-contrast story rows
    roundup_data = RoundupCardText(
        label="RADAR",
        headline="Signals in AI",
        remaining_titles=["Item 1", "Item 2"],
        cta="Listen to full episode",
        footer="FRONTIER PULSE · EPISODE 4"
    )
    with pytest.raises(ValueError, match="Contrast validation failed for 'roundup_story_rows'"):
        render_roundup_card(roundup_data, color_overrides={"row_title_fg": (36, 32, 29)})

