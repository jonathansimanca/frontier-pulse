"""Visual Asset Generator for Frontier Pulse.

Generates 4-asset Editorial Earth Tactile mobile video cards (1080x1350 px, 4:5 aspect ratio)
combining deterministic Pillow typography compositing, the Pulse character system,
tactile textures, and AI-generated artwork backgrounds.
"""

import os
import re
import json
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from src.config import (
    get_edition_dir,
    OUTPUT_DIR,
    get_genai_client,
    GEMINI_DEFAULT_MODEL,
    PODCAST_LANGUAGE_ES,
)
from src.schemas import (
    VisualAssetManifest,
    VisualAssetItem,
    CoverCardText,
    InsightCardText,
    EditionContextCardText,
    RoundupCardText,
)
from src.visual_theme import (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    SAFE_MARGIN_X,
    SAFE_MARGIN_Y,
    CONTENT_WIDTH,
    COLOR_BG_CHARCOAL,
    COLOR_SURFACE_INK,
    COLOR_TEXT_IVORY,
    COLOR_TEXT_SAND,
    COLOR_ACCENT_TERRACOTTA,
    COLOR_ACCENT_APRICOT,
    COLOR_ACCENT_SAGE,
    COLOR_CARD_SURFACE_OPAQUE,
    COLOR_CARD_SURFACE_TRANSLUCENT,
    COLOR_CARD_BORDER_SUBTLE,
    COLOR_CARD_BORDER_TERRACOTTA,
    COLOR_CARD_BORDER_SAGE,
    FONT_SIZE_COVER_HEADLINE,
    FONT_SIZE_INSIGHT_HEADLINE,
    FONT_SIZE_ROUNDUP_HEADLINE,
    FONT_SIZE_BODY,
    FONT_SIZE_CTA,
    FONT_SIZE_META,
    FONT_SIZE_LABEL,
    FONT_SIZE_FOOTER,
    HEADLINE_LINE_HEIGHT_RATIO,
    get_font,
    wrap_text,
)
from src.pulse_character import (
    composite_pulse_on_canvas,
    get_pulse_pose,
)
from src.tactile_texture import (
    apply_paper_grain,
    draw_terracotta_brush_stroke,
    draw_apricot_marker_underline,
    draw_sage_emphasis_mark,
)
from src.scene_prompt_builder import build_scene_prompt
from src.editorial_planner import (
    plan_editorial_cards,
    build_fallback_plan,
    slugify,
    clamp_words,
)


def get_episode_number(edition_date: Optional[str] = None) -> int:
    """Resolve sequential episode number from env, date anchors, or disk folders."""
    env_ep = os.getenv("EPISODE_NUMBER")
    if env_ep and env_ep.strip().isdigit():
        return int(env_ep.strip())

    known_editions = ["2026-08-05", "2026-08-12", "2026-08-18", "2026-08-24"]
    if edition_date and edition_date in known_editions:
        return known_editions.index(edition_date) + 1

    editions_dir = OUTPUT_DIR / "editions"
    if editions_dir.exists():
        found = sorted([
            p.name for p in editions_dir.iterdir()
            if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", p.name)
        ])
        if edition_date and edition_date in found:
            return found.index(edition_date) + 1
        elif found:
            return len(found) + 1

    return 4


def create_base_gradient_background(scene_mode: str = "neutral") -> Image.Image:
    """Generate a warm Editorial Earth Tactile gradient background."""
    img = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), COLOR_BG_CHARCOAL + (255,))
    draw = ImageDraw.Draw(img)

    # Vertical background gradient from Surface Ink to Charcoal
    r1, g1, b1 = COLOR_SURFACE_INK
    r2, g2, b2 = COLOR_BG_CHARCOAL
    for y in range(CANVAS_HEIGHT):
        ratio = y / CANVAS_HEIGHT
        r = int(r1 * (1 - ratio) + r2 * ratio)
        g = int(g1 * (1 - ratio) + g2 * ratio)
        b = int(b1 * (1 - ratio) + b2 * ratio)
        draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(r, g, b, 255))

    # Soft ambient atmospheric warm glow in upper canvas
    glow = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy = CANVAS_WIDTH // 2, int(CANVAS_HEIGHT * 0.35)
    
    glow_color = COLOR_ACCENT_TERRACOTTA if scene_mode in ["alert", "builder"] else COLOR_ACCENT_APRICOT
    glow_draw.ellipse(
        [cx - 380, cy - 280, cx + 380, cy + 280],
        fill=(glow_color[0], glow_color[1], glow_color[2], 35)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img, glow)

    return img


def draw_rounded_card(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int = 20,
    fill: Tuple[int, int, int, int] = COLOR_CARD_SURFACE_OPAQUE,
    outline: Optional[Tuple[int, int, int, int]] = COLOR_CARD_BORDER_SUBTLE,
    width: int = 1
) -> None:
    """Draw a rounded card container surface with high contrast."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def apply_dark_scrim(canvas: Image.Image, bottom_scrim_height: int = 700) -> Image.Image:
    """Apply dark gradient scrim to preserve high contrast for text overlays."""
    scrim = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)

    # Top scrim
    for y in range(250):
        alpha = int(200 * (1 - y / 250))
        scrim_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(COLOR_BG_CHARCOAL[0], COLOR_BG_CHARCOAL[1], COLOR_BG_CHARCOAL[2], alpha))

    # Bottom scrim
    start_y = CANVAS_HEIGHT - bottom_scrim_height
    for y in range(start_y, CANVAS_HEIGHT):
        progress = (y - start_y) / float(bottom_scrim_height)
        alpha = int(245 * (progress ** 1.2))
        scrim_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(COLOR_BG_CHARCOAL[0], COLOR_BG_CHARCOAL[1], COLOR_BG_CHARCOAL[2], alpha))

    return Image.alpha_composite(canvas, scrim)


def render_cover_card(
    cover_data: CoverCardText,
    background_image: Optional[Image.Image] = None,
    scene_mode: str = "neutral"
) -> Image.Image:
    """Deterministically render AR-01 Cover Card (1080x1350 px)."""
    if background_image is not None:
        canvas = background_image.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS).convert("RGBA")
        canvas = apply_dark_scrim(canvas, bottom_scrim_height=750)
    else:
        canvas = create_base_gradient_background(scene_mode=scene_mode)

    # Composite Pulse character in upper-right visual zone
    canvas = composite_pulse_on_canvas(canvas, mode=scene_mode, target_height=420, position=(580, 180), opacity=0.95)

    overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Top Series Badge & Format Subtitle
    top_y = SAFE_MARGIN_Y + 10
    font_series = get_font(FONT_SIZE_BODY, bold=True)
    font_format = get_font(20, bold=False)

    # Series pill badge
    series_text = cover_data.series.upper()
    s_bbox = draw.textbbox((0, 0), series_text, font=font_series)
    s_w = (s_bbox[2] - s_bbox[0]) + 36
    s_h = 44
    draw_rounded_card(
        draw,
        (SAFE_MARGIN_X, top_y, SAFE_MARGIN_X + s_w, top_y + s_h),
        radius=14,
        fill=(COLOR_ACCENT_TERRACOTTA[0], COLOR_ACCENT_TERRACOTTA[1], COLOR_ACCENT_TERRACOTTA[2], 230),
        outline=None
    )
    draw.text((SAFE_MARGIN_X + 18, top_y + 8), series_text, font=font_series, fill=COLOR_TEXT_IVORY)

    # Format line beneath series badge
    format_y = top_y + s_h + 10
    draw.text((SAFE_MARGIN_X, format_y), cover_data.format.upper(), font=font_format, fill=COLOR_TEXT_SAND)

    # 2. Main Headline Card Surface (Center-Bottom)
    headline_font = get_font(FONT_SIZE_COVER_HEADLINE, bold=True)
    wrapped_headline = wrap_text(cover_data.headline, headline_font, CONTENT_WIDTH - 60, draw)
    
    line_height = int(FONT_SIZE_COVER_HEADLINE * HEADLINE_LINE_HEIGHT_RATIO)
    headline_block_height = len(wrapped_headline) * line_height

    card_y = CANVAS_HEIGHT - SAFE_MARGIN_Y - 420 - (headline_block_height - 150)
    card_y = max(480, card_y)
    card_height = headline_block_height + 260
    card_box = (SAFE_MARGIN_X, card_y, CANVAS_WIDTH - SAFE_MARGIN_X, card_y + card_height)

    # Card Surface with high contrast ink background
    draw_rounded_card(draw, card_box, radius=24, fill=COLOR_CARD_SURFACE_OPAQUE, outline=COLOR_CARD_BORDER_TERRACOTTA, width=2)

    # Draw headline lines
    text_y = card_y + 35
    for line in wrapped_headline:
        draw.text((SAFE_MARGIN_X + 30, text_y), line, font=headline_font, fill=COLOR_TEXT_IVORY)
        text_y += line_height

    # Tactile accent gesture (Rough Terracotta brush stroke beneath headline container)
    draw_terracotta_brush_stroke(draw, (SAFE_MARGIN_X + 30, text_y + 8), (SAFE_MARGIN_X + 260, text_y + 12), stroke_width=8, opacity=200)

    # 3. Metadata Line (Episode & Duration)
    meta_y = text_y + 28
    font_meta = get_font(FONT_SIZE_META, bold=False)
    draw.text((SAFE_MARGIN_X + 30, meta_y), cover_data.metadata, font=font_meta, fill=COLOR_TEXT_SAND)

    # 4. CTA Button (Ivory on Terracotta)
    cta_y = meta_y + 48
    font_cta = get_font(FONT_SIZE_CTA, bold=True)
    cta_text = cover_data.cta.strip()
    cta_bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
    cta_w = (cta_bbox[2] - cta_bbox[0]) + 48
    cta_h = 56

    cta_box = (SAFE_MARGIN_X + 30, cta_y, SAFE_MARGIN_X + 30 + cta_w, cta_y + cta_h)
    draw_rounded_card(
        draw,
        cta_box,
        radius=16,
        fill=(COLOR_ACCENT_TERRACOTTA[0], COLOR_ACCENT_TERRACOTTA[1], COLOR_ACCENT_TERRACOTTA[2], 255),
        outline=None
    )
    draw.text((SAFE_MARGIN_X + 54, cta_y + 11), cta_text, font=font_cta, fill=COLOR_TEXT_IVORY)

    # Combine layers and apply tactile paper grain overlay
    combined = Image.alpha_composite(canvas, overlay)
    grained = apply_paper_grain(combined, intensity=0.035)

    return grained.convert("RGB")


def render_insight_card(
    insight_data: InsightCardText,
    background_image: Optional[Image.Image] = None,
    scene_mode: str = "analyst",
    accent_border: Tuple[int, int, int] = COLOR_ACCENT_TERRACOTTA
) -> Image.Image:
    """Deterministically render AR-02 / AR-03 News Insight Card (1080x1350 px)."""
    if background_image is not None:
        canvas = background_image.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS).convert("RGBA")
        canvas = apply_dark_scrim(canvas, bottom_scrim_height=800)
    else:
        canvas = create_base_gradient_background(scene_mode=scene_mode)

    # Composite Pulse character in upper right
    canvas = composite_pulse_on_canvas(canvas, mode=scene_mode, target_height=380, position=(620, 160), opacity=0.90)

    overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Top Badge / Topic Label (Sage / Apricot accent)
    top_y = SAFE_MARGIN_Y + 10
    font_badge = get_font(FONT_SIZE_LABEL, bold=True)
    badge_label = insight_data.label.upper()
    badge_bbox = draw.textbbox((0, 0), badge_label, font=font_badge)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 32
    badge_h = 42

    draw_rounded_card(
        draw,
        (SAFE_MARGIN_X, top_y, SAFE_MARGIN_X + badge_w, top_y + badge_h),
        radius=12,
        fill=(COLOR_ACCENT_SAGE[0], COLOR_ACCENT_SAGE[1], COLOR_ACCENT_SAGE[2], 220),
        outline=None
    )
    draw.text((SAFE_MARGIN_X + 16, top_y + 8), badge_label, font=font_badge, fill=COLOR_TEXT_IVORY)

    # 2. Headline / Title (64 px, bold Ivory text, max 8 words)
    title_y = top_y + badge_h + 24
    font_title = get_font(FONT_SIZE_INSIGHT_HEADLINE, bold=True)
    title_lines = wrap_text(insight_data.title, font_title, CONTENT_WIDTH - 200, draw)
    
    title_lh = int(FONT_SIZE_INSIGHT_HEADLINE * HEADLINE_LINE_HEIGHT_RATIO)
    for line in title_lines:
        draw.text((SAFE_MARGIN_X, title_y), line, font=font_title, fill=COLOR_TEXT_IVORY)
        title_y += title_lh

    # 3. Key Fact Container
    fact_card_y = title_y + 30
    font_fact_label = get_font(20, bold=True)
    font_fact_text = get_font(FONT_SIZE_BODY, bold=False)

    fact_lines = wrap_text(insight_data.key_fact, font_fact_text, CONTENT_WIDTH - 60, draw)
    fact_lh = 42
    fact_box_h = 45 + (len(fact_lines) * fact_lh) + 25
    fact_box = (SAFE_MARGIN_X, fact_card_y, CANVAS_WIDTH - SAFE_MARGIN_X, fact_card_y + fact_box_h)

    draw_rounded_card(draw, fact_box, radius=20, fill=COLOR_CARD_SURFACE_OPAQUE, outline=COLOR_CARD_BORDER_SUBTLE, width=1)
    
    # Spanish label HECHO CLAVE (no bilingual text)
    draw.text((SAFE_MARGIN_X + 30, fact_card_y + 20), "HECHO CLAVE", font=font_fact_label, fill=COLOR_TEXT_SAND)
    fact_text_y = fact_card_y + 55
    for line in fact_lines:
        draw.text((SAFE_MARGIN_X + 30, fact_text_y), line, font=font_fact_text, fill=COLOR_TEXT_IVORY)
        fact_text_y += fact_lh

    # 4. Why It Matters Container (Highlighted with Terracotta Accent Border)
    why_card_y = fact_card_y + fact_box_h + 22
    font_why_text = get_font(FONT_SIZE_BODY, bold=False)
    font_why_bold = get_font(FONT_SIZE_BODY, bold=True)

    why_text = insight_data.why_it_matters.strip()
    why_lines = wrap_text(why_text, font_why_text, CONTENT_WIDTH - 60, draw)
    why_lh = 42
    why_box_h = 30 + (len(why_lines) * why_lh) + 25
    why_box = (SAFE_MARGIN_X, why_card_y, CANVAS_WIDTH - SAFE_MARGIN_X, why_card_y + why_box_h)

    draw_rounded_card(
        draw,
        why_box,
        radius=20,
        fill=COLOR_CARD_SURFACE_OPAQUE,
        outline=(accent_border[0], accent_border[1], accent_border[2], 180),
        width=2
    )

    why_text_y = why_card_y + 24
    for line_idx, line in enumerate(why_lines):
        if line_idx == 0 and line.startswith("POR QUÉ IMPORTA:"):
            prefix = "POR QUÉ IMPORTA:"
            rest = line[len(prefix):].lstrip()
            draw.text((SAFE_MARGIN_X + 30, why_text_y), prefix, font=font_why_bold, fill=COLOR_ACCENT_TERRACOTTA)
            prefix_bbox = draw.textbbox((SAFE_MARGIN_X + 30, why_text_y), prefix, font=font_why_bold)
            draw.text((prefix_bbox[2] + 10, why_text_y), rest, font=font_why_text, fill=COLOR_TEXT_IVORY)
        else:
            draw.text((SAFE_MARGIN_X + 30, why_text_y), line, font=font_why_text, fill=COLOR_TEXT_IVORY)
        why_text_y += why_lh

    # 5. Footer Line (Fixed at bottom safe margin)
    footer_y = CANVAS_HEIGHT - SAFE_MARGIN_Y - 30
    font_footer = get_font(FONT_SIZE_FOOTER, bold=True)
    draw.text((SAFE_MARGIN_X, footer_y), insight_data.footer.upper(), font=font_footer, fill=COLOR_TEXT_SAND)

    combined = Image.alpha_composite(canvas, overlay)
    grained = apply_paper_grain(combined, intensity=0.035)

    return grained.convert("RGB")


def render_context_card(
    context_data: EditionContextCardText,
    background_image: Optional[Image.Image] = None,
    scene_mode: str = "analyst"
) -> Image.Image:
    """Render AR-03 Fallback Context Card when fewer than 2 news items are present."""
    insight_proxy = InsightCardText(
        label=context_data.label,
        title=context_data.title,
        key_fact=context_data.context_text,
        why_it_matters="POR QUÉ IMPORTA: Análisis y perspectiva para el equipo.",
        footer=context_data.footer
    )
    return render_insight_card(insight_proxy, background_image=background_image, scene_mode=scene_mode, accent_border=COLOR_ACCENT_APRICOT)


def render_roundup_card(
    roundup_data: RoundupCardText,
    background_image: Optional[Image.Image] = None
) -> Image.Image:
    """Deterministically render AR-04 Closing Radar Card (1080x1350 px)."""
    if background_image is not None:
        canvas = background_image.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS).convert("RGBA")
        canvas = apply_dark_scrim(canvas, bottom_scrim_height=900)
    else:
        canvas = create_base_gradient_background(scene_mode="narrator")

    # Composite Pulse in Narrator mode at microphone on the right side
    canvas = composite_pulse_on_canvas(canvas, mode="narrator", target_height=480, position=(560, 320), opacity=0.98)

    overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Top Radar Label Badge
    top_y = SAFE_MARGIN_Y + 10
    font_badge = get_font(FONT_SIZE_LABEL, bold=True)
    badge_label = roundup_data.label.upper()
    badge_bbox = draw.textbbox((0, 0), badge_label, font=font_badge)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 32
    badge_h = 42

    draw_rounded_card(
        draw,
        (SAFE_MARGIN_X, top_y, SAFE_MARGIN_X + badge_w, top_y + badge_h),
        radius=12,
        fill=(COLOR_ACCENT_TERRACOTTA[0], COLOR_ACCENT_TERRACOTTA[1], COLOR_ACCENT_TERRACOTTA[2], 230),
        outline=None
    )
    draw.text((SAFE_MARGIN_X + 16, top_y + 8), badge_label, font=font_badge, fill=COLOR_TEXT_IVORY)

    # 2. Main Headline
    title_y = top_y + badge_h + 24
    font_title = get_font(FONT_SIZE_ROUNDUP_HEADLINE, bold=True)
    title_lines = wrap_text(roundup_data.headline, font_title, CONTENT_WIDTH, draw)
    title_lh = int(FONT_SIZE_ROUNDUP_HEADLINE * HEADLINE_LINE_HEIGHT_RATIO)
    for line in title_lines:
        draw.text((SAFE_MARGIN_X, title_y), line, font=font_title, fill=COLOR_TEXT_IVORY)
        title_y += title_lh

    # 3. Clean Left Column: Remaining News Items
    items_start_y = title_y + 40
    font_item = get_font(28, bold=False)
    font_num = get_font(22, bold=True)
    left_column_width = 490

    current_item_y = items_start_y
    for idx, title in enumerate(roundup_data.remaining_titles, 1):
        item_lines = wrap_text(title, font_item, left_column_width - 80, draw)
        box_h = max(70, len(item_lines) * 36 + 26)
        item_box = (SAFE_MARGIN_X, current_item_y, SAFE_MARGIN_X + left_column_width, current_item_y + box_h)

        # Draw mini row container
        draw_rounded_card(draw, item_box, radius=14, fill=COLOR_CARD_SURFACE_OPAQUE, outline=COLOR_CARD_BORDER_SUBTLE, width=1)

        # Number circle badge
        num_circle_box = [SAFE_MARGIN_X + 16, current_item_y + 14, SAFE_MARGIN_X + 50, current_item_y + 48]
        draw.ellipse(num_circle_box, fill=COLOR_ACCENT_TERRACOTTA)
        draw.text((SAFE_MARGIN_X + 27, current_item_y + 18), str(idx), font=font_num, fill=COLOR_TEXT_IVORY)

        # Title text lines
        line_y = current_item_y + 16
        for l in item_lines:
            draw.text((SAFE_MARGIN_X + 66, line_y), l, font=font_item, fill=COLOR_TEXT_IVORY)
            line_y += 36

        current_item_y += box_h + 16

    # 4. CTA Button (Escucha el episodio completo)
    cta_y = max(current_item_y + 35, CANVAS_HEIGHT - SAFE_MARGIN_Y - 140)
    font_cta = get_font(FONT_SIZE_CTA, bold=True)
    cta_text = roundup_data.cta.strip()
    cta_bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
    cta_w = (cta_bbox[2] - cta_bbox[0]) + 48
    cta_h = 58

    cta_box = (SAFE_MARGIN_X, cta_y, SAFE_MARGIN_X + cta_w, cta_y + cta_h)
    draw_rounded_card(
        draw,
        cta_box,
        radius=16,
        fill=(COLOR_ACCENT_TERRACOTTA[0], COLOR_ACCENT_TERRACOTTA[1], COLOR_ACCENT_TERRACOTTA[2], 255),
        outline=None
    )
    draw.text((SAFE_MARGIN_X + 24, cta_y + 12), cta_text, font=font_cta, fill=COLOR_TEXT_IVORY)

    # 5. Footer
    footer_y = CANVAS_HEIGHT - SAFE_MARGIN_Y - 30
    font_footer = get_font(FONT_SIZE_FOOTER, bold=True)
    draw.text((SAFE_MARGIN_X, footer_y), roundup_data.footer.upper(), font=font_footer, fill=COLOR_TEXT_SAND)

    combined = Image.alpha_composite(canvas, overlay)
    grained = apply_paper_grain(combined, intensity=0.035)

    return grained.convert("RGB")


def generate_background_artwork(prompt: str) -> Optional[Image.Image]:
    """Generate AI background artwork without readable text using Gemini Image Generation or Imagen 3."""
    try:
        client = get_genai_client()
        clean_prompt = prompt.strip()
        
        # 1. Try gemini-3.1-flash-image
        try:
            resp = client.models.generate_content(
                model="gemini-3.1-flash-image",
                contents=clean_prompt,
            )
            if resp.candidates and resp.candidates[0].content:
                for part in resp.candidates[0].content.parts:
                    if getattr(part, "inline_data", None) and part.inline_data.data:
                        from io import BytesIO
                        raw_bytes = part.inline_data.data
                        if isinstance(raw_bytes, str):
                            raw_bytes = base64.b64decode(raw_bytes)
                        return Image.open(BytesIO(raw_bytes))
        except Exception as e:
            print(f"[visual_asset_generator] Flash image background call failed: {e}")

        # 2. Try imagen-3.0-generate-002
        try:
            resp = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=clean_prompt,
                config={
                    "number_of_images": 1,
                    "aspect_ratio": "4:5",
                    "output_mime_type": "image/png"
                }
            )
            if resp.generated_images:
                from io import BytesIO
                return Image.open(BytesIO(resp.generated_images[0].image.image_bytes))
        except Exception as e:
            print(f"[visual_asset_generator] Imagen background call failed: {e}")

    except Exception as e:
        print(f"[visual_asset_generator] Image generation client error: {e}")

    return None


def generate_visual_assets(
    news_data: dict,
    edition_date: str,
    episode_number: Optional[int] = None,
    audio_duration_minutes: Optional[int] = 4,
    language: str = PODCAST_LANGUAGE_ES
) -> Tuple[VisualAssetManifest, dict]:
    """Generate all 4 visual assets (Cover + Insight Cards + Roundup + Manifest) for an edition.

    Outputs:
    - episode-[number]-01-cover.png
    - episode-[number]-02-insight-[slug-a].png
    - episode-[number]-03-insight-[slug-b].png (or context fallback)
    - episode-[number]-04-news-roundup.png
    - episode-[number]-assets.json
    - podcast_cover.jpg (for backward compatibility with Telegram publisher)
    """
    edition_dir = get_edition_dir(edition_date)
    ep_num = episode_number or get_episode_number(edition_date)
    dur_min = audio_duration_minutes or 4
    lang_code = "es" if "es" in language.lower() else "en"

    # 1. Formulate 4-card editorial plan
    plan = plan_editorial_cards(
        news_data=news_data,
        episode_number=ep_num,
        duration_minutes=dur_min,
        language=lang_code
    )

    manifest_assets: List[VisualAssetItem] = []
    generated_file_paths: dict = {}
    footer_text = f"FRONTIER PULSE · EPISODIO {ep_num}" if lang_code == "es" else f"FRONTIER PULSE · EPISODE {ep_num}"

    # ==========================================================================
    # 2. Render AR-01 Cover Card
    # ==========================================================================
    cover_info = plan["cover"]
    cover_meta = f"Episodio {ep_num} · {dur_min} min" if lang_code == "es" else f"Episode {ep_num} · {dur_min} min"
    cover_cta = "▶ Escuchar ahora" if lang_code == "es" else "▶ Listen now"
    cover_format = "PODCAST SEMANAL DE IA" if lang_code == "es" else "WEEKLY AI PODCAST"

    cover_text_model = CoverCardText(
        series="FRONTIER PULSE",
        format=cover_format,
        headline=cover_info["headline"],
        metadata=cover_meta,
        cta=cover_cta
    )

    prompt_cover = build_scene_prompt("cover", cover_info.get("scene_mode", "neutral"), cover_info.get("scene_subject"))
    bg_cover = generate_background_artwork(prompt_cover)
    cover_img = render_cover_card(cover_text_model, background_image=bg_cover, scene_mode=cover_info.get("scene_mode", "neutral"))

    cover_filename = f"episode-{ep_num}-01-cover.png"
    cover_path = edition_dir / cover_filename
    cover_img.save(cover_path, format="PNG")
    generated_file_paths["cover"] = cover_path

    # Save backward-compatible podcast_cover.jpg in edition and legacy output dirs
    jpg_path_edition = edition_dir / "podcast_cover.jpg"
    jpg_path_legacy = OUTPUT_DIR / "podcast_cover.jpg"
    cover_img.save(jpg_path_edition, format="JPEG", quality=92)
    cover_img.save(jpg_path_legacy, format="JPEG", quality=92)
    generated_file_paths["podcast_cover_jpg"] = jpg_path_edition

    manifest_assets.append(
        VisualAssetItem(
            file=cover_filename,
            type="cover",
            display_order=1,
            suggested_screen_time_seconds=3,
            text=cover_text_model
        )
    )

    # ==========================================================================
    # 3. Render AR-02 News Insight Card A
    # ==========================================================================
    story_a = plan["story_a"]
    slug_a = story_a["slug"]
    label_a = "ESTA SEMANA EN IA" if lang_code == "es" else "THIS WEEK IN AI"

    insight_a_text_model = InsightCardText(
        label=label_a,
        title=story_a["title"],
        key_fact=story_a["key_fact"],
        why_it_matters=story_a["why_it_matters"],
        footer=footer_text
    )

    prompt_a = build_scene_prompt("insight", story_a.get("scene_mode", "analyst"), story_a.get("scene_subject"))
    bg_a = generate_background_artwork(prompt_a)
    insight_a_img = render_insight_card(
        insight_a_text_model,
        background_image=bg_a,
        scene_mode=story_a.get("scene_mode", "analyst"),
        accent_border=COLOR_ACCENT_TERRACOTTA
    )

    insight_a_filename = f"episode-{ep_num}-02-insight-{slug_a}.png"
    insight_a_path = edition_dir / insight_a_filename
    insight_a_img.save(insight_a_path, format="PNG")
    generated_file_paths["insight_a"] = insight_a_path

    manifest_assets.append(
        VisualAssetItem(
            file=insight_a_filename,
            type="news_insight",
            display_order=2,
            suggested_screen_time_seconds=5,
            text=insight_a_text_model,
            source_reference=story_a.get("source_reference")
        )
    )

    # ==========================================================================
    # 4. Render AR-03 News Insight Card B (or Fallback Context)
    # ==========================================================================
    story_b = plan["story_b"]
    slug_b = story_b["slug"]
    is_fallback_context = story_b.get("is_fallback_context", False)

    prompt_b = build_scene_prompt("insight", story_b.get("scene_mode", "analyst"), story_b.get("scene_subject"))
    bg_b = generate_background_artwork(prompt_b)

    if is_fallback_context:
        context_text_model = EditionContextCardText(
            label="CONTEXTO DE LA EDICIÓN" if lang_code == "es" else "EDITION CONTEXT",
            title=story_b["title"],
            context_text=story_b["key_fact"],
            cta="▶ Escucha el episodio completo" if lang_code == "es" else "▶ Listen to the full episode",
            footer=footer_text
        )
        insight_b_img = render_context_card(context_text_model, background_image=bg_b, scene_mode=story_b.get("scene_mode", "analyst"))
        card_b_filename = f"episode-{ep_num}-03-insight-{slug_b}.png"
        card_b_path = edition_dir / card_b_filename
        insight_b_img.save(card_b_path, format="PNG")
        generated_file_paths["insight_b"] = card_b_path

        manifest_assets.append(
            VisualAssetItem(
                file=card_b_filename,
                type="edition_context",
                display_order=3,
                suggested_screen_time_seconds=5,
                text=context_text_model,
                source_reference=story_b.get("source_reference")
            )
        )
    else:
        insight_b_text_model = InsightCardText(
            label=label_a,
            title=story_b["title"],
            key_fact=story_b["key_fact"],
            why_it_matters=story_b["why_it_matters"],
            footer=footer_text
        )
        insight_b_img = render_insight_card(
            insight_b_text_model,
            background_image=bg_b,
            scene_mode=story_b.get("scene_mode", "analyst"),
            accent_border=COLOR_ACCENT_APRICOT
        )
        card_b_filename = f"episode-{ep_num}-03-insight-{slug_b}.png"
        card_b_path = edition_dir / card_b_filename
        insight_b_img.save(card_b_path, format="PNG")
        generated_file_paths["insight_b"] = card_b_path

        manifest_assets.append(
            VisualAssetItem(
                file=card_b_filename,
                type="news_insight",
                display_order=3,
                suggested_screen_time_seconds=5,
                text=insight_b_text_model,
                source_reference=story_b.get("source_reference")
            )
        )

    # ==========================================================================
    # 5. Render AR-04 Closing Radar Card (news_roundup)
    # ==========================================================================
    roundup_info = plan["roundup"]
    roundup_label = "RADAR DE CIERRE" if lang_code == "es" else "CLOSING RADAR"
    roundup_headline = "Más señales que debes tener en el radar" if lang_code == "es" else "More signals to keep on your radar"
    roundup_cta = "Escucha el episodio completo" if lang_code == "es" else "Listen to the full episode"

    roundup_text_model = RoundupCardText(
        label=roundup_label,
        headline=roundup_headline,
        remaining_titles=roundup_info["remaining_titles"],
        cta=roundup_cta,
        footer=footer_text
    )

    prompt_roundup = build_scene_prompt("roundup", "narrator", roundup_info.get("scene_subject"))
    bg_roundup = generate_background_artwork(prompt_roundup)
    roundup_img = render_roundup_card(roundup_text_model, background_image=bg_roundup)

    roundup_filename = f"episode-{ep_num}-04-news-roundup.png"
    roundup_path = edition_dir / roundup_filename
    roundup_img.save(roundup_path, format="PNG")
    generated_file_paths["roundup"] = roundup_path

    manifest_assets.append(
        VisualAssetItem(
            file=roundup_filename,
            type="news_roundup",
            display_order=4,
            suggested_screen_time_seconds=8,
            text=roundup_text_model
        )
    )

    # ==========================================================================
    # 6. Save Manifest JSON
    # ==========================================================================
    manifest = VisualAssetManifest(
        episode_number=ep_num,
        edition_date=edition_date,
        assets=manifest_assets
    )

    manifest_filename = f"episode-{ep_num}-assets.json"
    manifest_path = edition_dir / manifest_filename
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    generated_file_paths["assets_manifest"] = manifest_path

    return manifest, generated_file_paths
