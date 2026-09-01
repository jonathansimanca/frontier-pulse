"""Deterministic Scene Prompt Builder for Frontier Pulse.

Constructs no-text image generation prompts using fixed template fragments,
brand visual constraints, reserved text-safe zones, and narrative scene modes.
Adheres strictly to Section 9.3 requirements.
"""

from typing import Optional

BASE_STYLE_DIRECTIVE = (
    "Editorial technology publication illustration, tactile Editorial Earth style. "
    "Warm matte charcoal, rich terracotta, soft apricot highlights, and muted sage accents. "
    "Tactile paper texture, soft studio lighting, organic 3D objects with delicate shadows. "
    "Minimalist composition, uncluttered negative space."
)

NEGATIVE_PROMPT_DIRECTIVE = (
    "ABSOLUTELY NO readable text, NO words, NO letters, NO typography, NO watermark, NO logo, "
    "NO HUD interface, NO fake dashboard screens, NO neon glow, NO cyan/blue cyberspace grid, "
    "NO metallic chrome reflections."
)

SAFE_ZONE_DIRECTIVES = {
    "cover": "Keep the bottom 45% and top 15% clear with clean, low-detail dark charcoal negative space for typography overlays.",
    "insight": "Keep the bottom 55% clear with clean dark charcoal negative space for typography cards. Visual focus placed on upper canvas.",
    "roundup": "Keep the entire left 60% of the canvas clean and minimal with dark charcoal negative space for text rows. Character and microphone placed on the right side.",
}

MODE_DESCRIPTIONS = {
    "analyst": "Pulse the compact broadcast robot with ivory visor and terracotta fin thoughtfully inspecting a soft glowing geometric data prism.",
    "alert": "Pulse the compact broadcast robot reacting attentively with elevated terracotta fin and subtle acoustic signal waves.",
    "orchestrator": "Pulse the compact broadcast robot gracefully directing modular terracotta and apricot technical blocks.",
    "builder": "Pulse the compact broadcast robot assembling tactile geometric components with focused posture.",
    "narrator": "Pulse the compact broadcast robot standing at a vintage desk broadcast microphone with subtle sound wave arcs on the right side.",
    "neutral": "Pulse the compact broadcast robot in a calm, balanced editorial posture.",
}


def build_scene_prompt(
    asset_type: str,
    scene_mode: str = "neutral",
    scene_subject: Optional[str] = None
) -> str:
    """Construct a clean, deterministic scene prompt for image generation models."""
    norm_type = asset_type.lower().strip()
    if norm_type not in SAFE_ZONE_DIRECTIVES:
        if "cover" in norm_type:
            norm_type = "cover"
        elif "roundup" in norm_type:
            norm_type = "roundup"
        else:
            norm_type = "insight"

    safe_zone = SAFE_ZONE_DIRECTIVES[norm_type]
    mode_key = scene_mode.lower().strip()
    mode_desc = MODE_DESCRIPTIONS.get(mode_key, MODE_DESCRIPTIONS["neutral"])

    subject_part = f" Scene depicts: {scene_subject.strip()}." if scene_subject else ""
    character_part = f" Character element: {mode_desc}."

    final_prompt = (
        f"{BASE_STYLE_DIRECTIVE} {character_part}{subject_part} "
        f"{safe_zone} Aspect ratio 4:5 vertical portrait. {NEGATIVE_PROMPT_DIRECTIVE}"
    )

    return final_prompt
