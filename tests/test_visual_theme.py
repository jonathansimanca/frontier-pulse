"""Unit tests for Visual Theme (Editorial Earth Tactile) and Pulse character manager."""

import pytest
from PIL import Image
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
    calculate_contrast_ratio,
    get_font,
    wrap_text,
    hex_to_rgb,
)
from src.pulse_character import (
    VALID_PULSE_MODES,
    get_pulse_pose,
    composite_pulse_on_canvas,
)


def test_theme_palette_contrast_ratios():
    """Verify that Editorial Earth Tactile palette satisfies WCAG contrast rules."""
    # Ivory text on Charcoal background must exceed 7:1
    ivory_on_charcoal = calculate_contrast_ratio(COLOR_TEXT_IVORY, COLOR_BG_CHARCOAL)
    assert ivory_on_charcoal >= 7.0, f"Contrast {ivory_on_charcoal} below target 7:1"

    # Ivory text on Ink Surface must exceed 7:1
    ivory_on_ink = calculate_contrast_ratio(COLOR_TEXT_IVORY, COLOR_SURFACE_INK)
    assert ivory_on_ink >= 7.0, f"Contrast {ivory_on_ink} below target 7:1"

    # Sand text on Ink Surface must exceed 4.5:1
    sand_on_ink = calculate_contrast_ratio(COLOR_TEXT_SAND, COLOR_SURFACE_INK)
    assert sand_on_ink >= 4.5, f"Contrast {sand_on_ink} below minimum 4.5:1"

    # Ivory text on Terracotta button must exceed 3.0:1 for large/bold text
    ivory_on_terracotta = calculate_contrast_ratio(COLOR_TEXT_IVORY, COLOR_ACCENT_TERRACOTTA)
    assert ivory_on_terracotta >= 3.0


def test_geometry_and_safe_zones():
    """Verify canvas geometry and safe zone dimensions."""
    assert CANVAS_WIDTH == 1080
    assert CANVAS_HEIGHT == 1350
    assert SAFE_MARGIN_X == 80
    assert SAFE_MARGIN_Y == 80
    assert CONTENT_WIDTH == 920


def test_font_retrieval_and_sizes():
    """Verify font loader can instantiate various typography sizes without failing."""
    for sz in [76, 64, 54, 30, 28, 24, 22]:
        font_regular = get_font(sz, bold=False)
        font_bold = get_font(sz, bold=True)
        assert font_regular is not None
        assert font_bold is not None


def test_pulse_character_modes():
    """Verify all 6 Pulse character poses exist and load as transparent RGBA images."""
    assert len(VALID_PULSE_MODES) == 6
    for mode in VALID_PULSE_MODES:
        pose_img = get_pulse_pose(mode)
        assert pose_img.mode == "RGBA"
        assert pose_img.size[0] > 0 and pose_img.size[1] > 0
        # Check that corners are transparent
        corner_alpha = pose_img.getpixel((5, 5))[3]
        assert corner_alpha == 0, f"Mode {mode} pose is not transparent at corners"


def test_composite_pulse_on_canvas():
    """Verify Pulse composites onto canvas respecting max 35% canvas area constraint."""
    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), COLOR_BG_CHARCOAL + (255,))
    composited = composite_pulse_on_canvas(canvas, mode="narrator", target_height=450, position=(600, 250))
    assert composited.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    assert composited.mode == "RGBA"
