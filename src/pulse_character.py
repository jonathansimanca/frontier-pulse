"""Pulse Character Asset Manager for Frontier Pulse.

Provides curated transparent-background character pose assets across 6 narrative modes:
- analyst
- alert
- orchestrator
- builder
- neutral
- narrator

Adheres to composition constraints (<= 35% canvas area, text-safe isolation).
"""

from pathlib import Path
from typing import Dict, Optional, Tuple
from PIL import Image

ASSETS_DIR = Path(__file__).parent / "assets" / "pulse"

VALID_PULSE_MODES = [
    "analyst",
    "alert",
    "orchestrator",
    "builder",
    "neutral",
    "narrator",
]

_POSE_CACHE: Dict[str, Image.Image] = {}


def get_pulse_pose(mode: str) -> Image.Image:
    """Retrieve the transparent RGBA image for the requested Pulse character mode."""
    normalized_mode = mode.lower().strip()
    if normalized_mode not in VALID_PULSE_MODES:
        normalized_mode = "neutral"

    if normalized_mode in _POSE_CACHE:
        return _POSE_CACHE[normalized_mode].copy()

    pose_file = ASSETS_DIR / f"{normalized_mode}.png"
    if not pose_file.exists():
        # Fallback to generating on the fly if file missing
        from src.generate_pulse_poses import generate_all_poses
        generate_all_poses()

    if pose_file.exists():
        img = Image.open(pose_file).convert("RGBA")
        _POSE_CACHE[normalized_mode] = img
        return img.copy()

    # If still not found, fallback to neutral transparent blank
    blank = Image.new("RGBA", (800, 900), (0, 0, 0, 0))
    return blank


def composite_pulse_on_canvas(
    canvas: Image.Image,
    mode: str,
    target_height: int = 420,
    position: Tuple[int, int] = (620, 220),
    opacity: float = 1.0
) -> Image.Image:
    """Composite Pulse character pose into a target canvas image with proper scaling."""
    pose_img = get_pulse_pose(mode)
    
    # Calculate aspect-ratio preserved dimensions
    orig_w, orig_h = pose_img.size
    aspect = orig_w / orig_h
    scaled_w = int(target_height * aspect)
    scaled_h = target_height

    # Ensure max canvas coverage constraint (<= 35% canvas area = <= 510,300 px^2)
    canvas_w, canvas_h = canvas.size
    max_area = int(0.35 * canvas_w * canvas_h)
    actual_area = scaled_w * scaled_h
    if actual_area > max_area:
        scale_factor = (max_area / actual_area) ** 0.5
        scaled_w = int(scaled_w * scale_factor)
        scaled_h = int(scaled_h * scale_factor)

    resized_pose = pose_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    if opacity < 1.0:
        alpha = resized_pose.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        resized_pose.putalpha(alpha)

    # Composite into RGBA canvas
    rgba_canvas = canvas.convert("RGBA")
    paste_layer = Image.new("RGBA", rgba_canvas.size, (0, 0, 0, 0))
    paste_layer.paste(resized_pose, position, resized_pose)
    
    return Image.alpha_composite(rgba_canvas, paste_layer)
