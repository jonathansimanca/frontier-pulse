"""Generate curated transparent-background PNG poses for the Pulse character."""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR = Path(__file__).parent / "assets" / "pulse"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Theme Palette Colors
CHARCOAL_SHELL = (42, 35, 32, 255)
CHARCOAL_DARK = (27, 23, 21, 255)
CHARCOAL_HIGHLIGHT = (65, 54, 49, 255)
IVORY_VISOR = (245, 235, 221, 255)
IVORY_SHADOW = (220, 210, 195, 255)
TERRACOTTA_FIN = (201, 87, 61, 255)
TERRACOTTA_HIGHLIGHT = (225, 105, 78, 255)
APRICOT_ACCENT = (240, 163, 91, 255)
SAGE_ACCENT = (113, 138, 120, 255)
EYE_DARK = (30, 25, 22, 255)


def create_pulse_base(
    width: int = 800,
    height: int = 900,
    head_tilt_deg: float = 0.0,
    eye_style: str = "neutral",
    fin_angle: float = 0.0
) -> Image.Image:
    """Create the core Pulse body, asymmetric head, ivory visor, and terracotta fin."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center_x = width // 2
    body_center_y = int(height * 0.65)
    head_center_y = int(height * 0.40)

    # 1. Subtle ground drop shadow
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.ellipse(
        [center_x - 180, int(height * 0.86), center_x + 180, int(height * 0.94)],
        fill=(15, 12, 10, 120)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(15))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    # 2. Short Compact Body
    body_w = 260
    body_h = 220
    body_box = [center_x - body_w // 2, body_center_y - body_h // 2, center_x + body_w // 2, body_center_y + body_h // 2]
    # Body base
    draw.rounded_rectangle(body_box, radius=70, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=4)
    # 3. Compact Lower Base / Feet
    draw.rounded_rectangle([center_x - 100, body_center_y + 80, center_x - 30, body_center_y + 130], radius=20, fill=CHARCOAL_DARK, outline=CHARCOAL_HIGHLIGHT, width=2)
    draw.rounded_rectangle([center_x + 30, body_center_y + 80, center_x + 100, body_center_y + 130], radius=20, fill=CHARCOAL_DARK, outline=CHARCOAL_HIGHLIGHT, width=2)

    # 4. Asymmetric Rounded Head (Rendered on rotated layer for tilt)
    head_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(head_canvas)

    hx, hy = center_x, head_center_y
    head_w, head_h = 320, 240
    head_box = [hx - head_w // 2, hy - head_h // 2, hx + head_w // 2, hy + head_h // 2]
    
    # Rounded head shell
    h_draw.rounded_rectangle(head_box, radius=85, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=5)

    # Terracotta Signal Fin on top
    fin_base_y = hy - head_h // 2
    fin_poly = [
        (hx - 24, fin_base_y + 6),
        (hx + 8, fin_base_y - 65),
        (hx + 28, fin_base_y - 65),
        (hx + 18, fin_base_y + 6)
    ]
    h_draw.polygon(fin_poly, fill=TERRACOTTA_FIN, outline=TERRACOTTA_HIGHLIGHT)
    # Small antenna detail notch
    h_draw.ellipse([hx + 10, fin_base_y - 75, hx + 26, fin_base_y - 59], fill=TERRACOTTA_HIGHLIGHT)

    # Ivory Visor
    visor_w, visor_h = 240, 130
    visor_box = [hx - visor_w // 2, hy - visor_h // 2 + 10, hx + visor_w // 2, hy + visor_h // 2 + 10]
    h_draw.rounded_rectangle(visor_box, radius=45, fill=IVORY_VISOR, outline=IVORY_SHADOW, width=3)

    # Visor inner highlight bevel
    h_draw.arc([visor_box[0] + 10, visor_box[1] + 10, visor_box[2] - 10, visor_box[3] - 10], start=190, end=350, fill=(255, 255, 255, 180), width=2)

    # Expressive Geometric Eyes (No mouth)
    vx_center = hx
    vy_center = hy + 12

    if eye_style == "neutral":
        # Balanced expressive pill/oval eyes
        h_draw.rounded_rectangle([vx_center - 70, vy_center - 22, vx_center - 25, vy_center + 22], radius=16, fill=EYE_DARK)
        h_draw.rounded_rectangle([vx_center + 25, vy_center - 22, vx_center + 70, vy_center + 22], radius=16, fill=EYE_DARK)
        # Eye sparkle highlights
        h_draw.ellipse([vx_center - 60, vy_center - 15, vx_center - 45, vy_center], fill=APRICOT_ACCENT)
        h_draw.ellipse([vx_center + 35, vy_center - 15, vx_center + 50, vy_center], fill=APRICOT_ACCENT)

    elif eye_style == "analyst":
        # Focused analytical eyes with geometric reticle arc
        h_draw.rounded_rectangle([vx_center - 70, vy_center - 16, vx_center - 25, vy_center + 16], radius=10, fill=EYE_DARK)
        h_draw.rounded_rectangle([vx_center + 25, vy_center - 24, vx_center + 70, vy_center + 24], radius=16, fill=EYE_DARK)
        # Reticle focus arc on right eye
        h_draw.arc([vx_center + 20, vy_center - 30, vx_center + 75, vy_center + 30], start=40, end=240, fill=SAGE_ACCENT, width=3)
        h_draw.ellipse([vx_center - 55, vy_center - 10, vx_center - 40, vy_center + 5], fill=APRICOT_ACCENT)

    elif eye_style == "alert":
        # Wide alert geometric circular eyes
        h_draw.ellipse([vx_center - 72, vy_center - 28, vx_center - 22, vy_center + 28], fill=EYE_DARK, outline=TERRACOTTA_FIN, width=3)
        h_draw.ellipse([vx_center + 22, vy_center - 28, vx_center + 72, vy_center + 28], fill=EYE_DARK, outline=TERRACOTTA_FIN, width=3)
        h_draw.ellipse([vx_center - 58, vy_center - 14, vx_center - 36, vy_center + 8], fill=TERRACOTTA_FIN)
        h_draw.ellipse([vx_center + 36, vy_center - 14, vx_center + 58, vy_center + 8], fill=TERRACOTTA_FIN)

    elif eye_style == "builder":
        # Confident, concentrated eyes
        h_draw.rounded_rectangle([vx_center - 68, vy_center - 24, vx_center - 26, vy_center + 14], radius=8, fill=EYE_DARK)
        h_draw.rounded_rectangle([vx_center + 26, vy_center - 24, vx_center + 68, vy_center + 14], radius=8, fill=EYE_DARK)
        h_draw.ellipse([vx_center - 52, vy_center - 14, vx_center - 38, vy_center], fill=APRICOT_ACCENT)
        h_draw.ellipse([vx_center + 42, vy_center - 14, vx_center + 56, vy_center], fill=APRICOT_ACCENT)

    elif eye_style == "orchestrator":
        # Dynamic active eyes looking outward
        h_draw.rounded_rectangle([vx_center - 72, vy_center - 20, vx_center - 24, vy_center + 20], radius=14, fill=EYE_DARK)
        h_draw.rounded_rectangle([vx_center + 24, vy_center - 20, vx_center + 72, vy_center + 20], radius=14, fill=EYE_DARK)
        h_draw.ellipse([vx_center - 45, vy_center - 10, vx_center - 32, vy_center + 6], fill=APRICOT_ACCENT)
        h_draw.ellipse([vx_center + 52, vy_center - 10, vx_center + 65, vy_center + 6], fill=APRICOT_ACCENT)

    elif eye_style == "narrator":
        # Warm communicative broadcast eyes
        h_draw.rounded_rectangle([vx_center - 68, vy_center - 22, vx_center - 26, vy_center + 22], radius=14, fill=EYE_DARK)
        h_draw.rounded_rectangle([vx_center + 26, vy_center - 22, vx_center + 68, vy_center + 22], radius=14, fill=EYE_DARK)
        h_draw.ellipse([vx_center - 55, vy_center - 14, vx_center - 40, vy_center + 2], fill=APRICOT_ACCENT)
        h_draw.ellipse([vx_center + 39, vy_center - 14, vx_center + 54, vy_center + 2], fill=APRICOT_ACCENT)

    # Apply head rotation if tilted
    if abs(head_tilt_deg) > 0.1:
        head_canvas = head_canvas.rotate(head_tilt_deg, resample=Image.Resampling.BICUBIC, center=(hx, hy))

    img = Image.alpha_composite(img, head_canvas)
    return img


def generate_pose_neutral() -> Image.Image:
    """Mode 5: Neutral/Reaction pose."""
    img = create_pulse_base(head_tilt_deg=0.0, eye_style="neutral")
    draw = ImageDraw.Draw(img)
    cx, cy = 400, 580

    # Arms in relaxed, friendly resting posture
    draw.rounded_rectangle([cx - 190, cy - 40, cx - 130, cy + 60], radius=24, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)
    draw.rounded_rectangle([cx + 130, cy - 40, cx + 190, cy + 60], radius=24, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)
    # Subtle apricot joint dots
    draw.ellipse([cx - 165, cy - 25, cx - 150, cy - 10], fill=TERRACOTTA_FIN)
    draw.ellipse([cx + 150, cy - 25, cx + 165, cy - 10], fill=TERRACOTTA_FIN)
    return img


def generate_pose_analyst() -> Image.Image:
    """Mode 1: Analyst inspecting an technical prism/module."""
    img = create_pulse_base(head_tilt_deg=6.0, eye_style="analyst")
    draw = ImageDraw.Draw(img)
    cx, cy = 400, 580

    # Left arm resting, Right arm raised holding/inspecting
    draw.rounded_rectangle([cx - 180, cy - 30, cx - 130, cy + 60], radius=20, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)
    draw.rounded_rectangle([cx + 120, cy - 80, cx + 180, cy + 20], radius=20, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)

    # Floating analytical geometric prism (Sage & Apricot)
    px, py = cx + 220, cy - 120
    prism_pts = [(px, py - 45), (px + 45, py), (px, py + 45), (px - 45, py)]
    draw.polygon(prism_pts, fill=(113, 138, 120, 220), outline=SAGE_ACCENT)
    draw.polygon([(px, py - 45), (px + 45, py), (px, py)], fill=APRICOT_ACCENT)
    # Dotted analytical beam
    for step in range(5):
        bx = cx + 110 + step * 18
        by = cy - 20 - step * 16
        draw.ellipse([bx - 3, by - 3, bx + 3, by + 3], fill=APRICOT_ACCENT)
    return img


def generate_pose_alert() -> Image.Image:
    """Mode 2: Alert reacting to disruptive or major news."""
    img = create_pulse_base(head_tilt_deg=-3.0, eye_style="alert")
    draw = ImageDraw.Draw(img)
    cx, cy = 400, 580

    # Both arms raised slightly outward in reactive posture
    draw.rounded_rectangle([cx - 210, cy - 70, cx - 150, cy + 20], radius=22, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)
    draw.rounded_rectangle([cx + 150, cy - 70, cx + 210, cy + 20], radius=22, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)

    # Terracotta signal pulse accent rings around fin
    fx, fy = cx, 280
    draw.arc([fx - 60, fy - 60, fx + 60, fy + 60], start=210, end=330, fill=TERRACOTTA_FIN, width=4)
    draw.arc([fx - 90, fy - 90, fx + 90, fy + 90], start=220, end=320, fill=APRICOT_ACCENT, width=3)
    return img


def generate_pose_orchestrator() -> Image.Image:
    """Mode 3: Orchestrator arranging connecting module blocks."""
    img = create_pulse_base(head_tilt_deg=0.0, eye_style="orchestrator")
    draw = ImageDraw.Draw(img)
    cx, cy = 400, 580

    # Arms outstretched orchestrating
    draw.rounded_rectangle([cx - 200, cy - 50, cx - 140, cy + 30], radius=20, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)
    draw.rounded_rectangle([cx + 140, cy - 50, cx + 200, cy + 30], radius=20, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)

    # 3 Floating connected module blocks
    b1 = [cx - 230, cy - 120, cx - 180, cy - 70]
    b2 = [cx, cy - 190, cx + 50, cy - 140]
    b3 = [cx + 200, cy - 110, cx + 250, cy - 60]

    draw.rounded_rectangle(b1, radius=10, fill=TERRACOTTA_FIN, outline=TERRACOTTA_HIGHLIGHT, width=2)
    draw.rounded_rectangle(b2, radius=10, fill=APRICOT_ACCENT, outline=(255, 200, 140, 255), width=2)
    draw.rounded_rectangle(b3, radius=10, fill=SAGE_ACCENT, outline=(150, 180, 160, 255), width=2)

    # Connecting workflow lines
    draw.line([(b1[2], b1[1] + 25), (b2[0], b2[1] + 25)], fill=TERRACOTTA_FIN, width=3)
    draw.line([(b2[2], b2[1] + 25), (b3[0], b3[1] + 25)], fill=APRICOT_ACCENT, width=3)
    return img


def generate_pose_builder() -> Image.Image:
    """Mode 4: Builder assembling/testing components."""
    img = create_pulse_base(head_tilt_deg=-5.0, eye_style="builder")
    draw = ImageDraw.Draw(img)
    cx, cy = 400, 580

    # Arms holding an assembly cube
    draw.rounded_rectangle([cx - 170, cy - 20, cx - 110, cy + 50], radius=18, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)
    draw.rounded_rectangle([cx + 110, cy - 40, cx + 170, cy + 40], radius=18, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)

    # Assembled component in center front
    cube_box = [cx - 40, cy - 10, cx + 40, cy + 70]
    draw.rounded_rectangle(cube_box, radius=12, fill=APRICOT_ACCENT, outline=TERRACOTTA_FIN, width=3)
    draw.line([cx - 20, cy + 30, cx + 20, cy + 30], fill=CHARCOAL_DARK, width=4)
    # Small tool indicator
    draw.polygon([(cx + 50, cy - 10), (cx + 80, cy - 30), (cx + 70, cy - 5)], fill=TERRACOTTA_FIN)
    return img


def generate_pose_narrator() -> Image.Image:
    """Mode 6: Narrator at desk broadcast microphone (for closing radar AR-04)."""
    img = create_pulse_base(head_tilt_deg=4.0, eye_style="narrator")
    draw = ImageDraw.Draw(img)
    cx, cy = 400, 580

    # Right arm resting comfortably, Left arm near desk/mic
    draw.rounded_rectangle([cx - 180, cy - 30, cx - 120, cy + 50], radius=20, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)
    draw.rounded_rectangle([cx + 120, cy - 30, cx + 180, cy + 50], radius=20, fill=CHARCOAL_SHELL, outline=CHARCOAL_HIGHLIGHT, width=3)

    # Vintage Desk Broadcast Microphone on Left/Center
    mx, my = cx - 140, cy + 60
    # Mic Base & Stand
    draw.rounded_rectangle([mx - 40, my + 80, mx + 40, my + 95], radius=6, fill=CHARCOAL_DARK, outline=TERRACOTTA_FIN, width=2)
    draw.rectangle([mx - 6, my + 10, mx + 6, my + 80], fill=TERRACOTTA_FIN)
    # Mic Capsule
    draw.rounded_rectangle([mx - 28, my - 50, mx + 28, my + 10], radius=20, fill=CHARCOAL_SHELL, outline=IVORY_VISOR, width=3)
    # Mic grill pattern
    for gy in range(my - 40, my + 5, 8):
        draw.line([mx - 18, gy, mx + 18, gy], fill=APRICOT_ACCENT, width=2)
    # Broadcast signal arcs
    draw.arc([mx + 35, my - 55, mx + 75, my - 15], start=-60, end=60, fill=TERRACOTTA_FIN, width=3)
    draw.arc([mx + 50, my - 70, mx + 100, my], start=-60, end=60, fill=APRICOT_ACCENT, width=2)
    return img


def generate_all_poses():
    """Build and save the complete suite of 6 curated Pulse pose PNGs."""
    poses = {
        "analyst.png": generate_pose_analyst(),
        "alert.png": generate_pose_alert(),
        "orchestrator.png": generate_pose_orchestrator(),
        "builder.png": generate_pose_builder(),
        "neutral.png": generate_pose_neutral(),
        "narrator.png": generate_pose_narrator(),
    }

    for filename, img in poses.items():
        filepath = OUTPUT_DIR / filename
        img.save(filepath, format="PNG")
        print(f"[+] Saved Pulse pose: {filepath} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    generate_all_poses()
