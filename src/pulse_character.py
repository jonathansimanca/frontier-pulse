"""Pulse Character Asset Manager for Frontier Pulse.

Provides curated transparent-background character pose assets across 6 narrative modes:
- analyst
- alert
- orchestrator
- builder
- neutral
- narrator

Adheres to composition constraints (<= 35% canvas area, canvas bounds, forbidden-zone isolation).
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
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


def boxes_intersect(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> bool:
    """Check if two rectangles (x1, y1, x2, y2) overlap."""
    b1_x1, b1_y1, b1_x2, b1_y2 = box1
    b2_x1, b2_y1, b2_x2, b2_y2 = box2
    return not (b1_x2 <= b2_x1 or b1_x1 >= b2_x2 or b1_y2 <= b2_y1 or b1_y1 >= b2_y2)


def composite_pulse_on_canvas(
    canvas: Image.Image,
    mode: str,
    target_height: int = 420,
    position: Tuple[int, int] = (620, 220),
    opacity: float = 1.0,
    forbidden_zones: Optional[List[Tuple[int, int, int, int]]] = None,
    allow_auto_adjust: bool = True
) -> Image.Image:
    """Composite Pulse character pose into a target canvas image with strict boundary and collision enforcement.

    Args:
        canvas: Base PIL image (1080x1350).
        mode: Character narrative mode.
        target_height: Target rendered pixel height.
        position: Top-left coordinate (x, y).
        opacity: Alpha multiplier (0.0 to 1.0).
        forbidden_zones: List of (x1, y1, x2, y2) rectangles Pulse must NOT overlap.
        allow_auto_adjust: If True, automatically clamps/scales to resolve boundary or collision issues;
                           if False, raises ValueError on invalid placement.

    Returns:
        Composited PIL Image (RGBA or original mode).
    """
    pose_img = get_pulse_pose(mode)
    canvas_w, canvas_h = canvas.size
    orig_w, orig_h = pose_img.size
    aspect = orig_w / orig_h

    scaled_w = int(target_height * aspect)
    scaled_h = target_height

    # 1. Ensure max canvas coverage constraint (<= 35% canvas area = <= 510,300 px^2 for 1080x1350)
    max_area = int(0.35 * canvas_w * canvas_h)
    actual_area = scaled_w * scaled_h
    if actual_area > max_area:
        scale_factor = (max_area / actual_area) ** 0.5
        scaled_w = int(scaled_w * scale_factor)
        scaled_h = int(scaled_h * scale_factor)

    pos_x, pos_y = position

    # 2. Canvas boundary validation
    is_out_of_bounds = (
        pos_x < 0 or pos_y < 0 or
        (pos_x + scaled_w) > canvas_w or
        (pos_y + scaled_h) > canvas_h
    )

    if is_out_of_bounds:
        if not allow_auto_adjust:
            raise ValueError(
                f"Pulse placement at ({pos_x}, {pos_y}) with size ({scaled_w}, {scaled_h}) "
                f"exceeds canvas boundaries ({canvas_w}, {canvas_h})."
            )
        # Auto-adjust: clamp inside canvas
        pos_x = max(0, min(pos_x, canvas_w - scaled_w))
        pos_y = max(0, min(pos_y, canvas_h - scaled_h))

    # 3. Forbidden zones (text-safe / typography panels) collision validation
    if forbidden_zones:
        pulse_box = (pos_x, pos_y, pos_x + scaled_w, pos_y + scaled_h)
        overlapping_zones = [z for z in forbidden_zones if boxes_intersect(pulse_box, z)]

        if overlapping_zones:
            if not allow_auto_adjust:
                raise ValueError(
                    f"Pulse bounding box {pulse_box} overlaps forbidden zone(s): {overlapping_zones}"
                )
            # Try auto-adjusting: shift horizontally or vertically
            adjusted = False
            # Attempt shifting right if room exists
            for shift_x in [canvas_w - scaled_w - 40, 640, 680]:
                test_box = (shift_x, pos_y, shift_x + scaled_w, pos_y + scaled_h)
                if not any(boxes_intersect(test_box, z) for z in forbidden_zones) and shift_x + scaled_w <= canvas_w and shift_x >= 0:
                    pos_x = shift_x
                    adjusted = True
                    break

            if not adjusted:
                # Attempt scaling down slightly
                for scale_down in [0.85, 0.70]:
                    new_w = int(scaled_w * scale_down)
                    new_h = int(scaled_h * scale_down)
                    test_box = (pos_x, pos_y, pos_x + new_w, pos_y + new_h)
                    if not any(boxes_intersect(test_box, z) for z in forbidden_zones):
                        scaled_w, scaled_h = new_w, new_h
                        adjusted = True
                        break

            if not adjusted:
                # Final check if still overlaps
                pulse_box = (pos_x, pos_y, pos_x + scaled_w, pos_y + scaled_h)
                if any(boxes_intersect(pulse_box, z) for z in forbidden_zones):
                    raise ValueError(
                        f"Unable to auto-adjust Pulse placement {pulse_box} without colliding with forbidden zones {forbidden_zones}."
                    )

    # 4. Resize and composite
    resized_pose = pose_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    if opacity < 1.0:
        alpha = resized_pose.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        resized_pose.putalpha(alpha)

    rgba_canvas = canvas.convert("RGBA")
    paste_layer = Image.new("RGBA", rgba_canvas.size, (0, 0, 0, 0))
    paste_layer.paste(resized_pose, (pos_x, pos_y), resized_pose)
    
    return Image.alpha_composite(rgba_canvas, paste_layer)
