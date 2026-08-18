import os
import base64
import warnings
from pathlib import Path
from google.genai import types
from src.config import get_edition_dir, OUTPUT_DIR, get_genai_client
from src.ia_news_researcher import parse_json_from_response

# Suppress experimental/deprecation warning for generate_images
warnings.filterwarnings("ignore", message=".*generate_images method is deprecated.*")

IMAGE_MODEL_NAME = os.getenv("IMAGE_MODEL_NAME", "imagen-3.0-generate-002")

def generate_podcast_cover(news_data: dict, edition_date: str) -> Path | None:
    """Generate high-impact vertical cover art for the podcast based on today's news using Imagen 3."""
    print("\n[*] STAGE 3.5: Generating social media podcast cover art using Imagen 3...")
    
    try:
        client = get_genai_client()
    except Exception as e:
        print(f"[!] Warning: Failed to initialize Gemini client for image generation: {e}")
        return None

    # Step 1: Query Gemini to extract creative visual elements from the news
    print("[*] Calling Gemini to design visual metaphors matching today's news...")
    news_items = news_data.get("items", [])
    news_summary_str = ""
    for i, item in enumerate(news_items, 1):
        news_summary_str += f"- News Story {i}: {item.get('title')} ({item.get('category')}) - {item.get('summary')[:150]}\n"

    design_prompt = f"""
Analyze the following tech and AI news items for this week:
{news_summary_str}

We need to generate a spectacular vertical podcast cover art matching these topics. Provide 3 specific text fields to fill our image prompt template:
1. central_visual_element: A single high-impact central visual metaphor representing the main breakthrough or theme this week (e.g., "a glowing holographic neural network with a key floating inside", "a massive obsidian open-source monolith", "a cybernetic glowing mechanical hand holding a glowing core"). Keep it short (5-10 words).
2. news_visual_symbols: A list of 2-3 small, symbolic visual elements representing other news items of this week, designed to orbit around the center (e.g., "glowing digital code fragments, small hovering cybernetic hummingbirds"). Keep it short (10-15 words).
3. color_palette: A cohesive, premium color scheme (e.g., "deep electric violet, cybernetic teal, and brushed chrome highlights"). Keep it short (5-8 words).

Return your response STRICTLY as a raw JSON block with keys "central_visual_element", "news_visual_symbols", and "color_palette".
Do NOT include any extra markdown outside the ```json block.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=design_prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
            )
        )
        design_data = parse_json_from_response(response.text)
        central = design_data.get("central_visual_element", "a glowing futuristic digital brain")
        symbols = design_data.get("news_visual_symbols", "glowing streams of digital data")
        colors = design_data.get("color_palette", "deep electric blue and vibrant neon magenta")
        print(f"[+] Creative design generated successfully:")
        print(f"    - Central visual: {central}")
        print(f"    - Orbiting symbols: {symbols}")
        print(f"    - Color palette: {colors}")
    except Exception as e:
        print(f"[!] Warning: Failed to generate custom design parameters: {e}. Reverting to high-tech fallbacks.")
        central = "a glowing holographic digital neural network"
        symbols = "glowing streams of binary code and geometric lines"
        colors = "deep electric blue and neon violet"

    # Step 2: Build the complete customized image prompt using our base template
    full_prompt = f'A high-impact vertical cover art for a tech podcast titled "FRONTIER PULSE". In the center, {central}. Orbiting around the center are visual elements representing today\'s news: {symbols}. Color palette: {colors}. Dark ambient studio background with a polished dark obsidian grid floor, dramatic rim lighting, dynamic atmospheric haze, cinematic lighting, modern cyberpunk tech aesthetic. The text "FRONTIER PULSE" is clearly printed at the top center in a bold, clean, metallic futuristic sans-serif font. High resolution, ultra-detailed 3D render, 8k, aspect ratio 9:16.'
    
    print(f"[*] Prompt built for Cover Art Generation:\n    \"{full_prompt}\"")

    # Step 3: Call Image Generation model
    print("[*] Generating image via Gemini Image Generation (gemini-2.5-flash-image)...")
    edition_dir = get_edition_dir(edition_date)
    output_path = edition_dir / "podcast_cover.jpg"
    output_path_legacy = OUTPUT_DIR / "podcast_cover.jpg"

    # Attempt 1: Native Multimodal Image Generation on Vertex AI (gemini-2.5-flash-image)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            )
        )
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    if isinstance(image_bytes, str):
                        image_bytes = base64.b64decode(image_bytes)
                    with open(output_path, "wb") as f:
                        f.write(image_bytes)
                    with open(output_path_legacy, "wb") as f:
                        f.write(image_bytes)
                    print(f"[+] Successfully generated and saved podcast cover image via gemini-2.5-flash-image! ({len(image_bytes)} bytes)")
                    return output_path
    except Exception as e:
        err_msg = str(e).split("\n")[0][:120]
        print(f"[!] gemini-2.5-flash-image generation failed ({err_msg}). Trying fallback...")

    # Attempt 2: Vertex AI Imagen 3 (imagen-3.0-generate-002)
    try:
        result = client.models.generate_images(
            model=IMAGE_MODEL_NAME,
            prompt=full_prompt,
            config=dict(number_of_images=1, aspect_ratio="9:16", output_mime_type="image/jpeg"),
        )
        if result.generated_images:
            image_bytes = result.generated_images[0].image.image_bytes
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            with open(output_path_legacy, "wb") as f:
                f.write(image_bytes)
            print(f"[+] Successfully generated and saved podcast cover image via Imagen 3!")
            return output_path
    except Exception as e2:
        err_msg2 = str(e2).split("\n")[0][:120]
        print(f"[!] Imagen 3 generation failed: {err_msg2}")

    # Attempt 3: Interactions API (Nano Banana / AI Studio fallback)
    try:
        interaction = client.interactions.create(
            model="gemini-3.1-flash-image",
            input=full_prompt,
            response_format={
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": "9:16",
                "image_size": "2K"
            }
        )
        if interaction.output_image and interaction.output_image.data:
            image_bytes = base64.b64decode(interaction.output_image.data)
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            with open(output_path_legacy, "wb") as f:
                f.write(image_bytes)
            print(f"[+] Successfully generated and saved podcast cover image via Nano Banana!")
            return output_path
    except Exception as e3:
        err_msg3 = str(e3).split("\n")[0][:120]
        print(f"[!] Nano Banana interaction fallback failed: {err_msg3}")

    print("[!] Warning: Cover image generation skipped after exhausting all attempts.")
    return None
