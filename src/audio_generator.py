import json
import os
import sys
from pathlib import Path
from google.cloud import texttospeech
from google.auth.exceptions import DefaultCredentialsError

from src.config import (
    OUTPUT_DIR,
    PODCAST_LANGUAGE_ES,
    PODCAST_VOICE_NAME,
)


def load_spanish_script(script_path: Path = None) -> str:
    """Load the Spanish transcript text from the output directory."""
    if script_path is None:
        script_path = OUTPUT_DIR / "podcast_script_es.txt"

    if not script_path.exists():
        raise FileNotFoundError(f"Spanish script file not found at: {script_path}. Run script generator first.")

    with open(script_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def synthesize_speech(
    text: str,
    output_audio_path: Path = None,
    language_code: str = PODCAST_LANGUAGE_ES,
    voice_name: str = PODCAST_VOICE_NAME
) -> Path:
    """Synthesize speech audio from text using Google Cloud Text-to-Speech API with Latin American Spanish voice."""
    if output_audio_path is None:
        output_audio_path = OUTPUT_DIR / "frontier_pulse_episode.mp3"

    print("[*] Connecting to Google Cloud Text-to-Speech (ADC)...")
    
    try:
        client = texttospeech.TextToSpeechClient()
    except DefaultCredentialsError:
        print("\n[!] AUTHENTICATION ERROR:")
        print("Google Cloud Application Default Credentials (ADC) not found.")
        print("Run the following command in your terminal to authenticate:")
        print("   gcloud auth application-default login\n")
        sys.exit(1)

    # Configure input text
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Configure Latin American Spanish voice
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name,
        ssml_gender=texttospeech.SsmlVoiceGender.MALE
    )

    # Configure output audio encoding (MP3)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0
    )

    print(f"[*] Synthesizing audio with Latin American Spanish voice '{voice_name}'...")
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    # Save output audio file
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_audio_path, "wb") as out:
        out.write(response.audio_content)

    print(f"[+] Audio generated successfully.")
    print(f"[+] Saved to: {output_audio_path}")

    return output_audio_path


if __name__ == "__main__":
    script_text = load_spanish_script()
    synthesize_speech(script_text)
