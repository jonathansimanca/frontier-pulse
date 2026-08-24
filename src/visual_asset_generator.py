"""Visual Asset Generator for Frontier Pulse.

Generates LinkedIn mobile video visual cards (1080x1350 px, 4:5 aspect ratio)
combining AI-generated background artwork with deterministic Pillow typography compositing.
"""

import os
import re
import json
import base64
from pathlib import Path
from typing import List, Optional, Tuple, Union
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
    Edition,
    NewsItem,
)

# Dimensions & Safe Margins (AR: 4:5 for LinkedIn Mobile Video)
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350
SAFE_MARGIN_X = 80
SAFE_MARGIN_Y = 80
CONTENT_WIDTH = CANVAS_WIDTH - (2 * SAFE_MARGIN_X)

# Visual Theme Colors
COLOR_BG_DARK = (10, 15, 29)
COLOR_TEXT_PRIMARY = (255, 255, 255)
COLOR_TEXT_MUTED = (148, 163, 184)
COLOR_ACCENT_CYAN = (56, 189, 248)
COLOR_ACCENT_EMERALD = (52, 211, 153)
COLOR_ACCENT_AMBER = (251, 191, 36)
COLOR_ACCENT_VIOLET = (168, 85, 247)
COLOR_CARD_BG = (15, 23, 42, 220)
COLOR_CARD_BORDER = (51, 65, 85, 180)


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Retrieve a TrueType font with cross-platform fallback."""
    font_candidates = []
    if bold:
        font_candidates = [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "Arial-Bold.ttf",
            "Roboto-Bold.ttf",
            "arialbd.ttf",
            "Helvetica-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/seguisb.ttf",
        ]
    else:
        font_candidates = [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "Arial.ttf",
            "Roboto-Regular.ttf",
            "arial.ttf",
            "Helvetica.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue

    # Fallback to default FreeTypeFont
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Deterministically wrap text so each line fits within max_width pixels."""
    words = text.strip().split()
    if not words:
        return []

    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        line_width = bbox[2] - bbox[0]
        if line_width <= max_width or not current_line:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def create_base_gradient_background(accent_color: Tuple[int, int, int] = COLOR_ACCENT_CYAN) -> Image.Image:
    """Generate a premium dark technology ambient background image."""
    img = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), COLOR_BG_DARK)
    draw = ImageDraw.Draw(img)

    # Subtle top-to-bottom vertical gradient
    for y in range(CANVAS_HEIGHT):
        ratio = y / CANVAS_HEIGHT
        r = int(10 * (1 - ratio) + 5 * ratio)
        g = int(15 * (1 - ratio) + 8 * ratio)
        b = int(29 * (1 - ratio) + 18 * ratio)
        draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(r, g, b, 255))

    # Glow blob overlay
    glow = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    center_x, center_y = CANVAS_WIDTH // 2, CANVAS_HEIGHT // 3
    glow_color = (accent_color[0], accent_color[1], accent_color[2], 30)
    glow_draw.ellipse(
        [center_x - 350, center_y - 250, center_x + 350, center_y + 250],
        fill=glow_color
    )
    glow = glow.filter(ImageFilter.GaussianBlur(80))
    img = Image.alpha_composite(img, glow)

    # Subtle tech grid pattern
    grid_overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid_overlay)
    grid_size = 60
    for x in range(0, CANVAS_WIDTH, grid_size):
        grid_draw.line([(x, 0), (x, CANVAS_HEIGHT)], fill=(255, 255, 255, 6))
    for y in range(0, CANVAS_HEIGHT, grid_size):
        grid_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(255, 255, 255, 6))
    img = Image.alpha_composite(img, grid_overlay)

    return img


def draw_rounded_card(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int = 16,
    fill: Tuple[int, int, int, int] = COLOR_CARD_BG,
    outline: Optional[Tuple[int, int, int, int]] = COLOR_CARD_BORDER,
    width: int = 1
) -> None:
    """Draw a translucent rounded card container with optional border."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def render_cover_card(
    cover_data: CoverCardText,
    background_image: Optional[Image.Image] = None,
    accent_color: Tuple[int, int, int] = COLOR_ACCENT_CYAN
) -> Image.Image:
    """Deterministically render AR-01 Cover / Opening Card (1080x1350 px)."""
    if background_image is not None:
        canvas = background_image.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS).convert("RGBA")
        # Apply dark gradient scrim to ensure text legibility
        scrim = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        scrim_draw = ImageDraw.Draw(scrim)
        # Dark top gradient
        for y in range(350):
            alpha = int(220 * (1 - y / 350))
            scrim_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(5, 8, 17, alpha))
        # Dark bottom gradient
        for y in range(CANVAS_HEIGHT - 650, CANVAS_HEIGHT):
            progress = (y - (CANVAS_HEIGHT - 650)) / 650
            alpha = int(240 * progress)
            scrim_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(5, 8, 17, alpha))
        canvas = Image.alpha_composite(canvas, scrim)
    else:
        canvas = create_base_gradient_background(accent_color)

    # Overlay layer for text and cards
    overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Top Series & Format Label
    font_series = get_font(30, bold=True)
    font_format = get_font(20, bold=False)

    top_y = SAFE_MARGIN_Y + 10
    draw.text((SAFE_MARGIN_X, top_y), cover_data.series.upper(), font=font_series, fill=accent_color)
    
    bbox_series = draw.textbbox((SAFE_MARGIN_X, top_y), cover_data.series.upper(), font=font_series)
    format_y = bbox_series[3] + 8
    draw.text((SAFE_MARGIN_X, format_y), cover_data.format.upper(), font=font_format, fill=COLOR_TEXT_MUTED)

    # Accent decorative top-right indicator
    draw.rounded_rectangle(
        [CANVAS_WIDTH - SAFE_MARGIN_X - 110, top_y + 2, CANVAS_WIDTH - SAFE_MARGIN_X, top_y + 36],
        radius=17,
        fill=(accent_color[0], accent_color[1], accent_color[2], 40),
        outline=accent_color,
        width=1
    )
    font_badge = get_font(16, bold=True)
    draw.text((CANVAS_WIDTH - SAFE_MARGIN_X - 95, top_y + 10), "PODCAST", font=font_badge, fill=accent_color)

    # 2. Main Headline Card (Center-Bottom)
    headline_font = get_font(56, bold=True)
    wrapped_headline = wrap_text(cover_data.headline, headline_font, CONTENT_WIDTH - 60, draw)
    
    line_height = 70
    headline_block_height = len(wrapped_headline) * line_height

    card_y = CANVAS_HEIGHT - SAFE_MARGIN_Y - 380 - (headline_block_height - 140)
    card_y = max(450, card_y)
    card_height = headline_block_height + 250
    card_box = (SAFE_MARGIN_X, card_y, CANVAS_WIDTH - SAFE_MARGIN_X, card_y + card_height)

    # Draw semi-transparent card container
    draw_rounded_card(draw, card_box, radius=24, fill=(15, 23, 42, 230), outline=(accent_color[0], accent_color[1], accent_color[2], 120), width=2)

    # Draw Headline lines
    text_y = card_y + 35
    for line in wrapped_headline:
        draw.text((SAFE_MARGIN_X + 30, text_y), line, font=headline_font, fill=COLOR_TEXT_PRIMARY)
        text_y += line_height

    # 3. Metadata Line (Episode & Duration)
    meta_y = text_y + 20
    font_meta = get_font(26, bold=False)
    draw.text((SAFE_MARGIN_X + 30, meta_y), cover_data.metadata, font=font_meta, fill=COLOR_TEXT_MUTED)

    # 4. CTA Button
    cta_y = meta_y + 55
    font_cta = get_font(28, bold=True)
    cta_text = cover_data.cta.strip()
    cta_bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
    cta_w = (cta_bbox[2] - cta_bbox[0]) + 48
    cta_h = 56

    cta_box = (SAFE_MARGIN_X + 30, cta_y, SAFE_MARGIN_X + 30 + cta_w, cta_y + cta_h)
    draw_rounded_card(draw, cta_box, radius=16, fill=(accent_color[0], accent_color[1], accent_color[2], 255), outline=None)
    draw.text((SAFE_MARGIN_X + 54, cta_y + 12), cta_text, font=font_cta, fill=(10, 15, 29, 255))

    final_img = Image.alpha_composite(canvas, overlay)
    return final_img.convert("RGB")


def render_insight_card(
    insight_data: InsightCardText,
    background_image: Optional[Image.Image] = None,
    accent_color: Tuple[int, int, int] = COLOR_ACCENT_CYAN
) -> Image.Image:
    """Deterministically render AR-02 / AR-03 News Insight Card (1080x1350 px)."""
    if background_image is not None:
        canvas = background_image.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS).convert("RGBA")
        # Dark scrim to ensure contrast
        scrim = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        scrim_draw = ImageDraw.Draw(scrim)
        for y in range(CANVAS_HEIGHT):
            alpha = int(180 + 75 * (y / CANVAS_HEIGHT))
            scrim_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(5, 8, 17, min(255, alpha)))
        canvas = Image.alpha_composite(canvas, scrim)
    else:
        canvas = create_base_gradient_background(accent_color)

    overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Top Badge / Label (e.g., ESTA SEMANA EN IA)
    top_y = SAFE_MARGIN_Y + 10
    font_badge = get_font(22, bold=True)
    badge_label = insight_data.label.upper()
    badge_bbox = draw.textbbox((0, 0), badge_label, font=font_badge)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 36
    badge_h = 44

    draw_rounded_card(
        draw,
        (SAFE_MARGIN_X, top_y, SAFE_MARGIN_X + badge_w, top_y + badge_h),
        radius=14,
        fill=(accent_color[0], accent_color[1], accent_color[2], 45),
        outline=accent_color,
        width=1
    )
    draw.text((SAFE_MARGIN_X + 18, top_y + 10), badge_label, font=font_badge, fill=accent_color)

    # 2. Story Title (Plain language headline, max 9 words)
    title_y = top_y + badge_h + 30
    font_title = get_font(50, bold=True)
    title_lines = wrap_text(insight_data.title, font_title, CONTENT_WIDTH, draw)
    
    title_lh = 64
    for line in title_lines:
        draw.text((SAFE_MARGIN_X, title_y), line, font=font_title, fill=COLOR_TEXT_PRIMARY)
        title_y += title_lh

    # 3. Key Fact Container
    fact_card_y = title_y + 35
    font_fact_label = get_font(18, bold=True)
    font_fact_text = get_font(26, bold=False)

    fact_lines = wrap_text(insight_data.key_fact, font_fact_text, CONTENT_WIDTH - 60, draw)
    fact_lh = 38
    fact_box_h = 45 + (len(fact_lines) * fact_lh) + 30
    fact_box = (SAFE_MARGIN_X, fact_card_y, CANVAS_WIDTH - SAFE_MARGIN_X, fact_card_y + fact_box_h)

    draw_rounded_card(draw, fact_box, radius=20, fill=(15, 23, 42, 235), outline=COLOR_CARD_BORDER, width=1)
    
    # Fact label
    draw.text((SAFE_MARGIN_X + 30, fact_card_y + 20), "HECHO CLAVE / KEY FACT", font=font_fact_label, fill=COLOR_TEXT_MUTED)
    # Fact body text
    fact_text_y = fact_card_y + 55
    for line in fact_lines:
        draw.text((SAFE_MARGIN_X + 30, fact_text_y), line, font=font_fact_text, fill=(241, 245, 249))
        fact_text_y += fact_lh

    # 4. Why It Matters Container (Highlighted with Accent Border)
    why_card_y = fact_card_y + fact_box_h + 25
    font_why_text = get_font(26, bold=False)
    font_why_bold = get_font(26, bold=True)

    why_text = insight_data.why_it_matters.strip()
    why_lines = wrap_text(why_text, font_why_text, CONTENT_WIDTH - 60, draw)
    why_lh = 38
    why_box_h = 30 + (len(why_lines) * why_lh) + 30
    why_box = (SAFE_MARGIN_X, why_card_y, CANVAS_WIDTH - SAFE_MARGIN_X, why_card_y + why_box_h)

    draw_rounded_card(
        draw,
        why_box,
        radius=20,
        fill=(15, 23, 42, 240),
        outline=(accent_color[0], accent_color[1], accent_color[2], 180),
        width=2
    )

    why_text_y = why_card_y + 25
    for line_idx, line in enumerate(why_lines):
        if line_idx == 0 and (line.startswith("POR QUÉ IMPORTA:") or line.startswith("WHY IT MATTERS:")):
            prefix = "POR QUÉ IMPORTA:" if line.startswith("POR QUÉ IMPORTA:") else "WHY IT MATTERS:"
            rest = line[len(prefix):]
            draw.text((SAFE_MARGIN_X + 30, why_text_y), prefix, font=font_why_bold, fill=accent_color)
            prefix_bbox = draw.textbbox((SAFE_MARGIN_X + 30, why_text_y), prefix, font=font_why_bold)
            draw.text((prefix_bbox[2] + 8, why_text_y), rest, font=font_why_text, fill=COLOR_TEXT_PRIMARY)
        else:
            draw.text((SAFE_MARGIN_X + 30, why_text_y), line, font=font_why_text, fill=COLOR_TEXT_PRIMARY)
        why_text_y += why_lh

    # 5. Footer Line (Fixed at bottom safe margin)
    footer_y = CANVAS_HEIGHT - SAFE_MARGIN_Y - 30
    font_footer = get_font(20, bold=True)
    draw.text((SAFE_MARGIN_X, footer_y), insight_data.footer.upper(), font=font_footer, fill=COLOR_TEXT_MUTED)

    final_img = Image.alpha_composite(canvas, overlay)
    return final_img.convert("RGB")


def slugify(text: str, max_words: int = 3) -> str:
    """Convert text into a clean URL-friendly hyphenated slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    words = text.strip().split()[:max_words]
    slug = "-".join(words)
    return slug or "news"


def get_episode_number(edition_date: Optional[str] = None) -> int:
    """Resolve the sequential episode number for the given edition date.

    Supports EPISODE_NUMBER environment variable, anchors on known edition dates,
    or calculates sequentially based on historical folders.
    """
    env_ep = os.getenv("EPISODE_NUMBER")
    if env_ep and env_ep.strip().isdigit():
        return int(env_ep.strip())

    # Baseline sequence
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


def clamp_words(text: str, max_words: int) -> str:
    """Ensure a string does not exceed max_words."""
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words])


def plan_visual_card_contents(
    news_data: dict,
    episode_number: int,
    duration_minutes: int = 4,
    language: str = "es"
) -> dict:
    """Use Gemini 3.7 Flash to formulate structured, concise copy for visual cards."""
    items = news_data.get("items", [])
    if not items:
        raise ValueError("Cannot plan visual cards from empty news items.")

    primary_item = items[0]
    secondary_item = items[1] if len(items) > 1 else None

    # Deterministic baseline fallbacks
    fallback_headline = clamp_words(f"3 avances clave de IA esta semana", 10) if language == "es" else clamp_words("3 key AI developments this week", 10)
    
    fallback_story_a_title = clamp_words(primary_item.get("title", "Avance destacado en Inteligencia Artificial"), 9)
    fallback_story_a_fact = clamp_words(primary_item.get("summary", "Desarrollo relevante en el ecosistema de IA."), 20)
    why_raw_a = primary_item.get("why_it_matters", "Impacto directo en la productividad y arquitectura técnica.")
    fallback_story_a_why = clamp_words(f"POR QUÉ IMPORTA: {why_raw_a}", 16) if language == "es" else clamp_words(f"WHY IT MATTERS: {why_raw_a}", 16)
    slug_a = slugify(primary_item.get("id", primary_item.get("title", "ai-news")))

    source_a = "Frontier Pulse"
    if primary_item.get("sources") and len(primary_item["sources"]) > 0:
        source_a = str(primary_item["sources"][0].get("url", primary_item["sources"][0].get("publisher", "Frontier Pulse")))

    fallback_plan = {
        "cover": {
            "headline": fallback_headline,
            "visual_prompt": "Abstract geometric 3D network neural nodes floating in deep blue cyberspace, volumetric rim lighting, high-tech dark minimal aesthetic, no text."
        },
        "story_a": {
            "slug": slug_a,
            "title": fallback_story_a_title,
            "key_fact": fallback_story_a_fact,
            "why_it_matters": fallback_story_a_why,
            "source_reference": source_a,
            "visual_prompt": "Clean futuristic dark cyber interface with abstract glowing data streams, minimal high contrast, 3d render, no text."
        },
        "include_card_b": False,
        "story_b": None
    }

    if secondary_item:
        # Check if secondary item has a distinct category or high relevance
        is_distinct = secondary_item.get("category") != primary_item.get("category") or secondary_item.get("relevance_score", 0) >= 4
        if is_distinct:
            fallback_plan["include_card_b"] = True
            slug_b = slugify(secondary_item.get("id", secondary_item.get("title", "second-story")))
            source_b = "Frontier Pulse"
            if secondary_item.get("sources") and len(secondary_item["sources"]) > 0:
                source_b = str(secondary_item["sources"][0].get("url", secondary_item["sources"][0].get("publisher", "Frontier Pulse")))
            
            fallback_plan["story_b"] = {
                "slug": slug_b,
                "title": clamp_words(secondary_item.get("title", "Innovación técnica en modelos de lenguaje"), 9),
                "key_fact": clamp_words(secondary_item.get("summary", "Avance verificado en modelos de inteligencia artificial."), 20),
                "why_it_matters": clamp_words(f"POR QUÉ IMPORTA: {secondary_item.get('why_it_matters', 'Relevancia técnica inmediata.')}", 16) if language == "es" else clamp_words(f"WHY IT MATTERS: {secondary_item.get('why_it_matters', 'Technical relevance.')}", 16),
                "source_reference": source_b,
                "visual_prompt": "Modern high-tech data visualization particles in deep obsidian purple space, sleek glowing contours, no text."
            }

    # Attempt LLM structured formulation with Gemini
    try:
        client = get_genai_client()
        prompt = f"""You are the Lead Visual Designer and Editor for Frontier Pulse, a premier AI technology watch podcast.
Formulate structured copy and visual background prompts for 2 to 3 mobile video cards (1080x1350 px) based on this edition's news items.

Edition Title: {news_data.get('title', '')}
Language: Latin American Spanish ({language})
Items:
{json.dumps([{
    'id': it.get('id'),
    'title': it.get('title'),
    'category': it.get('category'),
    'summary': it.get('summary'),
    'why_it_matters': it.get('why_it_matters'),
    'relevance_score': it.get('relevance_score'),
    'sources': it.get('sources', [])
} for it in items[:3]], indent=2, ensure_ascii=False)}

CONSTRAINTS & RULES:
1. All card copy MUST be in Latin American Spanish.
2. Cover Card:
   - headline: EXACTLY 1 benefit-led headline explaining why this week matters. MAXIMUM 10 WORDS.
   - visual_prompt: Atmospheric 3D abstract concept prompt for the background illustration (NO text, NO letters, dark high-tech palette).
3. Story A (Primary Story):
   - slug: 2-3 word lowercase hyphenated topic slug (e.g. "astra-reasoning", "agentes-autonomos").
   - title: Plain-language headline. MAXIMUM 9 WORDS (no clickbait).
   - key_fact: 1 verifiable factual sentence describing what happened. MAXIMUM 20 WORDS.
   - why_it_matters: Short practical implication starting with "POR QUÉ IMPORTA: ". MAXIMUM 16 WORDS (including prefix).
   - visual_prompt: Abstract visual concept prompt for Story A background (NO text).
4. Story B (Optional Secondary Card):
   - include_card_b: true ONLY IF there is a second story that is substantively distinct from Story A and adds major standalone value. Otherwise false.
   - If true, provide slug, title (max 9 words), key_fact (max 20 words), why_it_matters (max 16 words, starting with "POR QUÉ IMPORTA: "), visual_prompt (NO text).

Respond strictly with valid JSON conforming to this JSON schema:
{{
  "cover": {{
    "headline": "string (<= 10 words)",
    "visual_prompt": "string"
  }},
  "story_a": {{
    "slug": "string",
    "title": "string (<= 9 words)",
    "key_fact": "string (<= 20 words)",
    "why_it_matters": "string (<= 16 words, starts with 'POR QUÉ IMPORTA: ')",
    "source_reference": "string",
    "visual_prompt": "string"
  }},
  "include_card_b": true,
  "story_b": {{
    "slug": "string",
    "title": "string (<= 9 words)",
    "key_fact": "string (<= 20 words)",
    "why_it_matters": "string (<= 16 words, starts with 'POR QUÉ IMPORTA: ')",
    "source_reference": "string",
    "visual_prompt": "string"
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

        plan_data = json.loads(response.text)
        
        # Validate and enforce strict bounds
        if "cover" in plan_data and "headline" in plan_data["cover"]:
            fallback_plan["cover"]["headline"] = clamp_words(plan_data["cover"]["headline"], 10)
            if plan_data["cover"].get("visual_prompt"):
                fallback_plan["cover"]["visual_prompt"] = plan_data["cover"]["visual_prompt"]

        if "story_a" in plan_data:
            sa = plan_data["story_a"]
            fallback_plan["story_a"]["title"] = clamp_words(sa.get("title", fallback_story_a_title), 9)
            fallback_plan["story_a"]["key_fact"] = clamp_words(sa.get("key_fact", fallback_story_a_fact), 20)
            why_a = sa.get("why_it_matters", fallback_story_a_why)
            if not why_a.startswith("POR QUÉ IMPORTA:"):
                why_a = f"POR QUÉ IMPORTA: {why_a}"
            fallback_plan["story_a"]["why_it_matters"] = clamp_words(why_a, 16)
            if sa.get("slug"):
                fallback_plan["story_a"]["slug"] = slugify(sa["slug"])
            if sa.get("visual_prompt"):
                fallback_plan["story_a"]["visual_prompt"] = sa["visual_prompt"]
            if sa.get("source_reference"):
                fallback_plan["story_a"]["source_reference"] = sa["source_reference"]

        if plan_data.get("include_card_b") and plan_data.get("story_b") and secondary_item:
            sb = plan_data["story_b"]
            fallback_plan["include_card_b"] = True
            why_b = sb.get("why_it_matters", "POR QUÉ IMPORTA: Avance relevante.")
            if not why_b.startswith("POR QUÉ IMPORTA:"):
                why_b = f"POR QUÉ IMPORTA: {why_b}"
            fallback_plan["story_b"] = {
                "slug": slugify(sb.get("slug", "secondary-story")),
                "title": clamp_words(sb.get("title", "Avance destacado"), 9),
                "key_fact": clamp_words(sb.get("key_fact", "Desarrollo técnico verificado."), 20),
                "why_it_matters": clamp_words(why_b, 16),
                "source_reference": sb.get("source_reference", fallback_plan.get("story_b", {}).get("source_reference", "Frontier Pulse")),
                "visual_prompt": sb.get("visual_prompt", "High tech minimal 3d graphic, dark background, no text.")
            }
        else:
            fallback_plan["include_card_b"] = False
            fallback_plan["story_b"] = None

    except Exception as e:
        print(f"[visual_asset_generator] Notice: Gemini card planning fallback used: {e}")

    return fallback_plan


def generate_background_artwork(prompt: str) -> Optional[Image.Image]:
    """Generate AI background illustration without text using Gemini or Imagen 3."""
    try:
        client = get_genai_client()
        clean_prompt = f"{prompt.strip()}. Atmospheric, minimalist 3D rendering, dark modern tech aesthetic, ultra high resolution, cinematic lighting, absolutely NO text, NO typography, NO watermark, NO letters, NO words."
        
        # Try gemini-3.1-flash-image
        try:
            resp = client.models.generate_content(
                model="gemini-3.1-flash-image",
                contents=clean_prompt,
            )
            for part in resp.candidates[0].content.parts:
                if part.inline_data:
                    from io import BytesIO
                    raw_bytes = part.inline_data.data
                    if isinstance(raw_bytes, str):
                        raw_bytes = base64.b64decode(raw_bytes)
                    return Image.open(BytesIO(raw_bytes))
        except Exception as e:
            print(f"[visual_asset_generator] Flash image background call failed: {e}")

        # Fallback to imagen-3.0-generate-002
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
    """Generate all visual assets (Cover + Insight Cards + Manifest) for an edition.

    Outputs:
    - episode-[number]-01-cover.png
    - episode-[number]-02-insight-[topic-a].png
    - episode-[number]-03-insight-[topic-b].png (optional)
    - episode-[number]-assets.json
    - podcast_cover.jpg (for backward compatibility with Telegram publisher)
    """
    edition_dir = get_edition_dir(edition_date)
    ep_num = episode_number or get_episode_number(edition_date)
    dur_min = audio_duration_minutes or 4

    # 1. Plan card contents
    plan = plan_visual_card_contents(
        news_data=news_data,
        episode_number=ep_num,
        duration_minutes=dur_min,
        language="es" if "es" in language.lower() else "en"
    )

    manifest_assets: List[VisualAssetItem] = []
    generated_file_paths: dict = {}

    # 2. Render AR-01 Cover Card
    cover_headline = plan["cover"]["headline"]
    cover_meta = f"Episodio {ep_num} · {dur_min} min" if "es" in language.lower() else f"Episode {ep_num} · {dur_min} min"
    cover_cta = "▶ Escuchar ahora" if "es" in language.lower() else "▶ Listen now"
    cover_format = "PODCAST SEMANAL DE NOTICIAS DE IA" if "es" in language.lower() else "WEEKLY AI NEWS PODCAST"

    cover_text_model = CoverCardText(
        series="FRONTIER PULSE",
        format=cover_format,
        headline=cover_headline,
        metadata=cover_meta,
        cta=cover_cta
    )

    # Generate background artwork for cover
    bg_cover = generate_background_artwork(plan["cover"]["visual_prompt"])
    cover_img = render_cover_card(cover_text_model, background_image=bg_cover, accent_color=COLOR_ACCENT_CYAN)

    cover_filename = f"episode-{ep_num}-01-cover.png"
    cover_path = edition_dir / cover_filename
    cover_img.save(cover_path, format="PNG")
    generated_file_paths["cover"] = cover_path

    manifest_assets.append(
        VisualAssetItem(
            file=cover_filename,
            type="cover",
            display_order=1,
            suggested_screen_time_seconds=3,
            text=cover_text_model
        )
    )

    # 3. Render AR-02 News Insight Card A
    story_a = plan["story_a"]
    slug_a = story_a["slug"]
    insight_a_label = "ESTA SEMANA EN IA" if "es" in language.lower() else "THIS WEEK IN AI"
    footer_text = f"FRONTIER PULSE · EPISODIO {ep_num}" if "es" in language.lower() else f"FRONTIER PULSE · EPISODE {ep_num}"

    insight_a_text_model = InsightCardText(
        label=insight_a_label,
        title=story_a["title"],
        key_fact=story_a["key_fact"],
        why_it_matters=story_a["why_it_matters"],
        footer=footer_text
    )

    bg_a = generate_background_artwork(story_a["visual_prompt"])
    insight_a_img = render_insight_card(insight_a_text_model, background_image=bg_a, accent_color=COLOR_ACCENT_CYAN)

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

    # 4. Render AR-03 News Insight Card B (Optional)
    if plan.get("include_card_b") and plan.get("story_b"):
        story_b = plan["story_b"]
        slug_b = story_b["slug"]
        insight_b_text_model = InsightCardText(
            label=insight_a_label,
            title=story_b["title"],
            key_fact=story_b["key_fact"],
            why_it_matters=story_b["why_it_matters"],
            footer=footer_text
        )

        bg_b = generate_background_artwork(story_b["visual_prompt"])
        insight_b_img = render_insight_card(insight_b_text_model, background_image=bg_b, accent_color=COLOR_ACCENT_VIOLET)

        insight_b_filename = f"episode-{ep_num}-03-insight-{slug_b}.png"
        insight_b_path = edition_dir / insight_b_filename
        insight_b_img.save(insight_b_path, format="PNG")
        generated_file_paths["insight_b"] = insight_b_path

        manifest_assets.append(
            VisualAssetItem(
                file=insight_b_filename,
                type="news_insight",
                display_order=3,
                suggested_screen_time_seconds=5,
                text=insight_b_text_model,
                source_reference=story_b.get("source_reference")
            )
        )

    # 5. Build and Save Visual Asset Manifest (JSON)
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
