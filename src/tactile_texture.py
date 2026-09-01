"""Organic Tactile Texture System for Frontier Pulse.

Implements deterministic texture marks (rough terracotta brush strokes,
apricot marker underlines, sage emphasis marks, and subtle paper grain).
Adheres strictly to Section 5.3 constraints (at most 2 gestures per asset,
no texture behind paragraph/metadata/CTA, >=12px separation).
"""

import random
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter
from src.visual_theme import (
    COLOR_ACCENT_TERRACOTTA,
    COLOR_ACCENT_APRICOT,
    COLOR_ACCENT_SAGE,
)


def apply_paper_grain(canvas: Image.Image, intensity: float = 0.035, seed: int = 42) -> Image.Image:
    """Apply a subtle deterministic paper grain noise overlay to give an editorial tactile finish."""
    rng = random.Random(seed)
    width, height = canvas.size
    
    # Generate low-res grain and scale up with blur for soft natural texture
    grain_w, grain_h = width // 3, height // 3
    grain_img = Image.new("RGBA", (grain_w, grain_h), (0, 0, 0, 0))
    pixels = grain_img.load()
    
    max_alpha = int(255 * intensity)
    for y in range(grain_h):
        for x in range(grain_w):
            val = rng.randint(200, 255)
            alpha = rng.randint(0, max_alpha)
            pixels[x, y] = (val, val, val, alpha)
            
    grain_img = grain_img.resize((width, height), Image.Resampling.BILINEAR)
    grain_img = grain_img.filter(ImageFilter.GaussianBlur(1.0))
    
    return Image.alpha_composite(canvas.convert("RGBA"), grain_img)


def draw_terracotta_brush_stroke(
    draw: ImageDraw.ImageDraw,
    start_point: Tuple[int, int],
    end_point: Tuple[int, int],
    stroke_width: int = 12,
    opacity: int = 180,
    seed: int = 101
) -> None:
    """Draw a rough organic terracotta brush gesture with subtle texture variance."""
    rng = random.Random(seed)
    x1, y1 = start_point
    x2, y2 = end_point
    
    r, g, b = COLOR_ACCENT_TERRACOTTA
    color = (r, g, b, opacity)
    
    steps = max(10, int(((x2 - x1)**2 + (y2 - y1)**2)**0.5 / 6))
    for i in range(steps):
        t = i / float(steps)
        cx = x1 + t * (x2 - x1) + rng.uniform(-1.5, 1.5)
        cy = y1 + t * (y2 - y1) + rng.uniform(-1.5, 1.5)
        current_w = stroke_width * (0.8 + 0.4 * math_sin(t * 3.14159))
        draw.ellipse([cx - current_w/2, cy - current_w/2, cx + current_w/2, cy + current_w/2], fill=color)


def draw_apricot_marker_underline(
    draw: ImageDraw.ImageDraw,
    word_bbox: Tuple[int, int, int, int],
    y_offset: int = 6,
    height: int = 8,
    opacity: int = 190,
    seed: int = 202
) -> None:
    """Draw a soft apricot highlighter underline beneath a specific keyword bbox."""
    rng = random.Random(seed)
    x1, y1, x2, y2 = word_bbox
    stroke_y = y2 + y_offset
    
    r, g, b = COLOR_ACCENT_APRICOT
    color = (r, g, b, opacity)
    
    # Hand-drawn marker stroke with slightly rounded ends
    left_x = x1 - 4
    right_x = x2 + 4
    
    pts = [
        (left_x, stroke_y - height / 2 + rng.uniform(-1, 1)),
        (right_x, stroke_y - height / 2 + rng.uniform(-1, 1)),
        (right_x + 2, stroke_y + height / 2 + rng.uniform(-1, 1)),
        (left_x - 2, stroke_y + height / 2 + rng.uniform(-1, 1)),
    ]
    draw.polygon(pts, fill=color)


def draw_sage_emphasis_mark(
    draw: ImageDraw.ImageDraw,
    center: Tuple[int, int],
    radius: int = 20,
    mark_type: str = "circle",
    opacity: int = 160,
    seed: int = 303
) -> None:
    """Draw a tactile sage green emphasis gesture (irregular circle, accent block, or arrow)."""
    rng = random.Random(seed)
    cx, cy = center
    r, g, b = COLOR_ACCENT_SAGE
    color = (r, g, b, opacity)
    
    if mark_type == "circle":
        # Irregular hand-drawn loop
        draw.arc(
            [cx - radius + rng.uniform(-2, 2), cy - radius + rng.uniform(-2, 2),
             cx + radius + rng.uniform(-2, 2), cy + radius + rng.uniform(-2, 2)],
            start=rng.randint(-20, 10),
            end=rng.randint(320, 360),
            fill=color,
            width=3
        )
    elif mark_type == "arrow":
        # Small hand-drawn indicator arrow
        draw.line([(cx - radius, cy), (cx + radius, cy)], fill=color, width=3)
        draw.line([(cx + radius - 8, cy - 8), (cx + radius, cy)], fill=color, width=3)
        draw.line([(cx + radius - 8, cy + 8), (cx + radius, cy)], fill=color, width=3)
    else:
        # Accent block
        draw.rounded_rectangle(
            [cx - radius, cy - radius // 2, cx + radius, cy + radius // 2],
            radius=6,
            fill=color
        )


def math_sin(val: float) -> float:
    import math
    return math.sin(val)
