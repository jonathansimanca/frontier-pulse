import re
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


def split_text_into_chunks(text: str, max_bytes: int = 4000) -> list[str]:
    """Split text into natural sentence-level chunks each under max_bytes to respect Google Cloud TTS 5000-byte limit."""
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    sentences = re.split(r'(?<=[.!?\n])\s+', text)
    chunks = []
    current_chunk = []
    current_bytes = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_bytes = len(sentence.encode("utf-8")) + 1
        if current_bytes + sentence_bytes > max_bytes and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_bytes = sentence_bytes
        else:
            current_chunk.append(sentence)
            current_bytes += sentence_bytes

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def synthesize_speech(
    text: str,
    output_audio_path: Path = None,
    language_code: str = PODCAST_LANGUAGE_ES,
    voice_name: str = PODCAST_VOICE_NAME
) -> Path:
    """Synthesize speech audio from text using Google Cloud Text-to-Speech API with automatic chunking for long text."""
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

    # Split text into chunks below TTS 5,000-byte request limit
    chunks = split_text_into_chunks(text, max_bytes=4000)
    print(f"[*] Synthesizing audio with Latin American Spanish voice '{voice_name}' ({len(chunks)} chunk{'s' if len(chunks) > 1 else ''})...")

    # Configure Latin American Spanish voice
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name,
    )

    # Configure output audio encoding (MP3)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0
    )

    combined_audio = bytearray()
    for idx, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            print(f"    -> Synthesizing chunk {idx}/{len(chunks)} ({len(chunk.encode('utf-8'))} bytes)...")
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        combined_audio.extend(response.audio_content)

    # Save output audio file
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_audio_path, "wb") as out:
        out.write(combined_audio)

    print(f"[+] Audio generated successfully ({len(combined_audio)} bytes).")
    print(f"[+] Saved to: {output_audio_path}")

    return output_audio_path


if __name__ == "__main__":
    script_text = load_spanish_script()
    synthesize_speech(script_text)
