"""Unit tests for Visual Theme (Editorial Earth Tactile), Contrast by Role, and Pulse Character Manager."""

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
    FONT_SIZE_COVER_HEADLINE,
    FONT_SIZE_INSIGHT_HEADLINE,
    FONT_SIZE_ROUNDUP_HEADLINE,
    FONT_SIZE_BODY,
    FONT_SIZE_CTA,
    FONT_SIZE_META,
    FONT_SIZE_LABEL,
    FONT_SIZE_FOOTER,
    calculate_contrast_ratio,
    validate_contrast_by_role,
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
    # Ivory text on Charcoal background must exceed 7:1 (AAA)
    ivory_on_charcoal = calculate_contrast_ratio(COLOR_TEXT_IVORY, COLOR_BG_CHARCOAL)
    assert ivory_on_charcoal >= 7.0, f"Contrast {ivory_on_charcoal} below target 7:1"

    # Ivory text on Ink Surface must exceed 7:1 (AAA)
    ivory_on_ink = calculate_contrast_ratio(COLOR_TEXT_IVORY, COLOR_SURFACE_INK)
    assert ivory_on_ink >= 7.0, f"Contrast {ivory_on_ink} below target 7:1"

    # Sand text on Ink Surface must exceed 4.5:1 (AA)
    sand_on_ink = calculate_contrast_ratio(COLOR_TEXT_SAND, COLOR_SURFACE_INK)
    assert sand_on_ink >= 4.5, f"Contrast {sand_on_ink} below minimum 4.5:1"

    # Ivory text on Terracotta button must exceed 3.0:1 for large/bold text (AA Large)
    ivory_on_terracotta = calculate_contrast_ratio(COLOR_TEXT_IVORY, COLOR_ACCENT_TERRACOTTA)
    assert ivory_on_terracotta >= 3.0


def test_role_based_contrast_validation():
    """Verify role-based contrast validation logic for body, large bold, and labels."""
    # Body text on dark surface must meet 4.5:1
    is_valid, ratio, details = validate_contrast_by_role(
        COLOR_TEXT_IVORY,
        COLOR_SURFACE_INK,
        role="body",
        font_size=FONT_SIZE_BODY,
        is_bold=False
    )
    assert is_valid
    assert ratio >= 7.0
    assert details["meets_target"] is True

    # CTA button (large bold) on terracotta must meet 3.0:1
    is_valid, ratio, details = validate_contrast_by_role(
        COLOR_TEXT_IVORY,
        COLOR_ACCENT_TERRACOTTA,
        role="large_bold",
        font_size=FONT_SIZE_CTA,
        is_bold=True
    )
    assert is_valid
    assert ratio >= 3.0

    # Low contrast pair for body text must fail validation
    is_valid, ratio, details = validate_contrast_by_role(
        COLOR_ACCENT_TERRACOTTA,
        COLOR_SURFACE_INK,
        role="body",
        font_size=16,
        is_bold=False
    )
    assert not is_valid


def test_geometry_and_safe_zones():
    """Verify canvas geometry and safe zone dimensions."""
    assert CANVAS_WIDTH == 1080
    assert CANVAS_HEIGHT == 1350
    assert SAFE_MARGIN_X == 80
    assert SAFE_MARGIN_Y == 80
    assert CONTENT_WIDTH == 920


def test_typography_scale_constants():
    """Verify approved minimum typography scale constants."""
    assert FONT_SIZE_COVER_HEADLINE == 76
    assert FONT_SIZE_INSIGHT_HEADLINE == 64
    assert FONT_SIZE_ROUNDUP_HEADLINE == 54
    assert FONT_SIZE_BODY == 30
    assert FONT_SIZE_CTA == 30
    assert FONT_SIZE_META == 28
    assert FONT_SIZE_LABEL == 24
    assert FONT_SIZE_FOOTER == 22


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
        corner_alpha = pose_img.getpixel((5, 5))[3]
        assert corner_alpha == 0, f"Mode {mode} pose is not transparent at corners"


def test_composite_pulse_on_canvas_boundaries_and_forbidden_zones():
    """Verify Pulse composites onto canvas with boundary checking and forbidden zone collision enforcement."""
    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), COLOR_BG_CHARCOAL + (255,))

    # 1. Normal valid placement
    composited = composite_pulse_on_canvas(
        canvas,
        mode="narrator",
        target_height=450,
        position=(600, 250),
        allow_auto_adjust=False
    )
    assert composited.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    # 2. Out-of-bounds placement with allow_auto_adjust=False raises ValueError
    with pytest.raises(ValueError, match="exceeds canvas boundaries"):
        composite_pulse_on_canvas(
            canvas,
            mode="analyst",
            target_height=400,
            position=(950, 1100),
            allow_auto_adjust=False
        )

    # 3. Out-of-bounds placement with allow_auto_adjust=True automatically clamps
    adjusted = composite_pulse_on_canvas(
        canvas,
        mode="analyst",
        target_height=400,
        position=(950, 1100),
        allow_auto_adjust=True
    )
    assert adjusted.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    # 4. Forbidden zone overlap with allow_auto_adjust=False raises ValueError
    forbidden = [(600, 200, 900, 600)]
    with pytest.raises(ValueError, match="overlaps forbidden zone"):
        composite_pulse_on_canvas(
            canvas,
            mode="analyst",
            target_height=350,
            position=(620, 220),
            forbidden_zones=forbidden,
            allow_auto_adjust=False
        )
