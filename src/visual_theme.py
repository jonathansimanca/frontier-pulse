"""Editorial Earth Tactile Visual Theme for Frontier Pulse.

Centralizes palette tokens, typography rules, canvas geometry,
role-based contrast ratio validation, and cross-platform font resolution.
"""

from typing import Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont


# ==============================================================================
# Canvas & Geometry Standards (LinkedIn Mobile Video 4:5 Portrait)
# ==============================================================================
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350
SAFE_MARGIN_X = 80
SAFE_MARGIN_Y = 80
CONTENT_WIDTH = CANVAS_WIDTH - (2 * SAFE_MARGIN_X)  # 920 px


# ==============================================================================
# Editorial Earth Tactile Color Palette
# ==============================================================================
HEX_BG_CHARCOAL = "#1B1715"
HEX_SURFACE_INK = "#2A2320"
HEX_TEXT_IVORY = "#F5EBDD"
HEX_TEXT_SAND = "#C8B9AC"
HEX_ACCENT_TERRACOTTA = "#C9573D"
HEX_ACCENT_APRICOT = "#F0A35B"
HEX_ACCENT_SAGE = "#718A78"

# RGB Tuples
COLOR_BG_CHARCOAL = (27, 23, 21)
COLOR_SURFACE_INK = (42, 35, 32)
COLOR_TEXT_IVORY = (245, 235, 221)
COLOR_TEXT_SAND = (200, 185, 172)
COLOR_ACCENT_TERRACOTTA = (201, 87, 61)
COLOR_ACCENT_APRICOT = (240, 163, 91)
COLOR_ACCENT_SAGE = (113, 138, 120)

# Card Backgrounds with Alpha
COLOR_CARD_SURFACE_OPAQUE = (42, 35, 32, 245)
COLOR_CARD_SURFACE_TRANSLUCENT = (42, 35, 32, 210)
COLOR_CARD_BORDER_SUBTLE = (200, 185, 172, 50)
COLOR_CARD_BORDER_TERRACOTTA = (201, 87, 61, 140)
COLOR_CARD_BORDER_SAGE = (113, 138, 120, 140)


# ==============================================================================
# Typography Scales & Content Limits (Approved Minimum Sizes)
# ==============================================================================
FONT_SIZE_COVER_HEADLINE = 76   # 76 px bold
FONT_SIZE_INSIGHT_HEADLINE = 64 # 64 px bold
FONT_SIZE_ROUNDUP_HEADLINE = 54 # 54 px bold
FONT_SIZE_BODY = 30             # 30 px regular/bold reading text
FONT_SIZE_CTA = 30              # 30 px bold
FONT_SIZE_META = 28             # 28 px
FONT_SIZE_LABEL = 24            # 24 px bold (format, badges, hecho clave)
FONT_SIZE_FOOTER = 22           # 22 px bold

HEADLINE_LINE_HEIGHT_RATIO = 1.10

MAX_WORDS_COVER_HEADLINE = 8
MAX_WORDS_INSIGHT_HEADLINE = 8
MAX_WORDS_KEY_FACT = 20
MAX_WORDS_WHY_IT_MATTERS = 16
MAX_WORDS_ROUNDUP_TITLE = 7


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert hex string (#RRGGBB) to RGB tuple."""
    hex_clean = hex_str.lstrip("#")
    return tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))


def calculate_luminance(rgb: Tuple[int, int, int]) -> float:
    """Calculate relative luminance for WCAG contrast ratio calculation."""
    def _channel_lum(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * _channel_lum(r) + 0.7152 * _channel_lum(g) + 0.0722 * _channel_lum(b)


def calculate_contrast_ratio(rgb1: Tuple[int, int, int], rgb2: Tuple[int, int, int]) -> float:
    """Calculate WCAG contrast ratio between two RGB colors (returns value from 1.0 to 21.0)."""
    lum1 = calculate_luminance(rgb1)
    lum2 = calculate_luminance(rgb2)
    brightest = max(lum1, lum2)
    darkest = min(lum1, lum2)
    return (brightest + 0.05) / (darkest + 0.05)


def validate_contrast_by_role(
    text_rgb: Tuple[int, int, int],
    bg_rgb: Tuple[int, int, int],
    role: str = "body",
    font_size: int = 30,
    is_bold: bool = False
) -> Tuple[bool, float, Dict[str, Union[float, bool, str]]]:
    """Enforce role-based contrast compliance.

    Rules:
    - "body" / "primary": requires minimum 4.5:1 (AA regular), target 7.0:1 (AAA).
    - "large_bold" / "cta" / "label": requires minimum 3.0:1 (AA large, >=24px bold or >=32px).
    - Returns (is_valid, contrast_ratio, details_dict).
    """
    ratio = calculate_contrast_ratio(text_rgb, bg_rgb)
    is_large = font_size >= 32 or (font_size >= 24 and is_bold)

    if role in ["body", "primary"]:
        min_required = 4.5
        is_valid = ratio >= min_required
        meets_target = ratio >= 7.0
    elif role in ["large_bold", "cta", "label"]:
        min_required = 3.0 if is_large else 4.5
        is_valid = ratio >= min_required
        meets_target = ratio >= 4.5
    else:
        min_required = 4.5
        is_valid = ratio >= min_required
        meets_target = ratio >= 7.0

    details = {
        "role": role,
        "font_size": font_size,
        "is_bold": is_bold,
        "is_large_text": is_large,
        "contrast_ratio": round(ratio, 2),
        "min_required": min_required,
        "meets_target": meets_target,
        "is_valid": is_valid
    }

    return is_valid, ratio, details


def assert_render_contrast(
    text_rgb: Tuple[int, int, int],
    bg_rgb: Tuple[int, int, int],
    role: str = "body",
    font_size: int = 30,
    is_bold: bool = False,
    element_name: str = "element"
) -> float:
    """Preflight contrast validation for a rendering element.

    Raises ValueError if the contrast ratio does not meet the role-based minimum.
    Returns the calculated contrast ratio.
    """
    is_valid, ratio, details = validate_contrast_by_role(
        text_rgb=text_rgb,
        bg_rgb=bg_rgb,
        role=role,
        font_size=font_size,
        is_bold=is_bold
    )
    if not is_valid:
        raise ValueError(
            f"Contrast validation failed for '{element_name}': ratio {ratio:.2f}:1 does not meet required "
            f"{details['min_required']}:1 (role='{role}', font_size={font_size}, is_bold={is_bold}). "
            f"Foreground={text_rgb}, Background={bg_rgb}."
        )
    return ratio


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
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Bold.ttf",
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
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
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
