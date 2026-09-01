"""Deterministic Scene Prompt Builder for Frontier Pulse.

Constructs no-text, character-free background image generation prompts using
fixed template fragments, brand visual constraints, reserved typography zones,
and compositional negative space instructions.
Adheres strictly to Section 9.3 and Character Isolation requirements.
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
    "NO metallic chrome reflections, NO people, NO human figures, NO robots, NO faces, NO characters, NO mascots."
)

SAFE_ZONE_DIRECTIVES = {
    "cover": (
        "Keep the bottom 45% and top 15% clear with clean, low-detail dark charcoal negative space for typography overlays. "
        "Reserve the right side for a separately composited editorial character. "
        "Keep this area uncluttered and free of people, robots, faces, or characters."
    ),
    "insight": (
        "Keep the top-left area and bottom 55% clear with clean dark charcoal negative space for typography cards. "
        "Reserve the upper-right area for a separately composited editorial character. "
        "Keep this area uncluttered and free of people, robots, faces, or characters. "
        "Place visual focus on symbolic tactile technical objects."
    ),
    "roundup": (
        "Keep the entire left 60% and bottom 20% of the canvas clean and minimal with dark charcoal negative space for text rows. "
        "Reserve the right 40% area for a separately composited editorial character. "
        "Keep this area uncluttered and free of people, robots, faces, or characters."
    ),
}

MODE_COMPOSITION_DIRECTIVES = {
    "analyst": "Compositional focus on a soft glowing geometric data prism with delicate reflections.",
    "alert": "Compositional focus on geometric architectural arches with subtle acoustic signal waves.",
    "orchestrator": "Compositional focus on modular terracotta and apricot technical blocks in graceful balance.",
    "builder": "Compositional focus on tactile geometric components assembled with precision.",
    "narrator": "Compositional focus on subtle sound wave arcs and studio broadcast ambiance.",
    "neutral": "Compositional focus on balanced minimal geometric forms.",
}


def build_scene_prompt(
    asset_type: str,
    scene_mode: str = "neutral",
    scene_subject: Optional[str] = None
) -> str:
    """Construct a clean, deterministic scene prompt for image generation models without rendering characters."""
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
    comp_desc = MODE_COMPOSITION_DIRECTIVES.get(mode_key, MODE_COMPOSITION_DIRECTIVES["neutral"])

    # Clean any accidental character references from subject
    clean_subject = ""
    if scene_subject:
        cleaned = scene_subject.strip()
        # Remove any leading 'Pulse analyzing/exploring/reviewing' phrasing
        cleaned = cleaned.replace("Pulse analyzing", "Analysis of")
        cleaned = cleaned.replace("Pulse exploring", "Exploration of")
        cleaned = cleaned.replace("Pulse reviewing", "Review of")
        cleaned = cleaned.replace("Pulse narrating", "Broadcasting")
        cleaned = cleaned.replace("Pulse", "symbolic scene")
        clean_subject = f" Scene depicts: {cleaned}."

    composition_part = f" Scene composition: {comp_desc}"

    final_prompt = (
        f"{BASE_STYLE_DIRECTIVE}{composition_part}{clean_subject} "
        f"{safe_zone} Aspect ratio 4:5 vertical portrait. {NEGATIVE_PROMPT_DIRECTIVE}"
    )

    return final_prompt
