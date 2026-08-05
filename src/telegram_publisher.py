import json
import os
import requests
from pathlib import Path
from src.config import (
    INPUT_DIR,
    OUTPUT_DIR,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    get_edition_dir,
)
from src.schemas import EditionManifest
from src.manifest_manager import create_or_load_manifest, update_manifest_stage, save_manifest_atomic


def load_current_news() -> dict:
    """Load news dataset from input directory."""
    input_file = INPUT_DIR / "current_news.json"
    if not input_file.exists():
        input_file = INPUT_DIR / "sample_news.json"

    if not input_file.exists():
        raise FileNotFoundError("No news data found to build Telegram message.")

    with open(input_file, "r", encoding="utf-8") as f:
        return json.load(f)


def escape_markdown_legacy(text: str) -> str:
    """Escape active characters in legacy Telegram Markdown that could cause parse errors.
    Active characters in Markdown parse_mode are: _, *, `, [
    """
    if not text:
        return ""
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


def sanitize_error_message(text: str) -> str:
    """Redact Telegram Bot Token from any error strings or logs."""
    if not text:
        return ""
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in text:
        text = text.replace(TELEGRAM_BOT_TOKEN, "<REDACTED_TELEGRAM_TOKEN>")
    return text


def format_telegram_message(news_data: dict) -> str:
    """Format structured news data into a clean, engaging Telegram Markdown message."""
    edition_date = news_data.get("edition_date", "")
    items = news_data.get("items", [])
    is_slow_week = news_data.get("is_slow_week", False)

    msg = f"🎙 *Frontier Pulse* — Edición {edition_date}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if is_slow_week:
        msg += "☕ *Edición de Continuidad (Semana Tranquila)*\n"
        msg += "Esta semana los laboratorios de frontera han tenido una actividad estable. A continuación los temas destacados:\n\n"

    for idx, item in enumerate(items, 1):
        title = escape_markdown_legacy(item.get("title", "Sin título"))
        category = escape_markdown_legacy(item.get("category", ""))
        takeaways = item.get("key_takeaways", [])

        msg += f"*{idx}. {title}*\n"
        if category:
            msg += f"🏷 _{category}_\n"

        for takeaway in takeaways:
            escaped_takeaway = escape_markdown_legacy(takeaway)
            msg += f"• {escaped_takeaway}\n"
        msg += "\n"

    msg += "🎧 *Escucha el episodio completo en el audio adjunto a continuación.*"
    return msg


def send_telegram_message(message_text: str) -> int | None:
    """Send text message to Telegram chat via Bot API. Returns the message_id on success, or None on failure."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[!] TELEGRAM NOT CONFIGURATION:")
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env.")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        res_data = response.json()
        msg_id = res_data.get("result", {}).get("message_id")
        print("[+] Telegram text summary sent successfully!")
        return msg_id
    except requests.exceptions.RequestException as e:
        sanitized_err = sanitize_error_message(str(e))
        print(f"[!] Failed to send Telegram message: {sanitized_err}")
        return None


def send_telegram_audio(audio_path: Path = None, episode_title: str = "Frontier Pulse Episode") -> int | None:
    """Upload audio MP3 file to Telegram chat via Bot API. Returns the message_id on success, or None on failure."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    if audio_path is None:
        audio_path = OUTPUT_DIR / "frontier_pulse_episode.mp3"

    if not audio_path.exists():
        print(f"[!] Audio file not found for Telegram upload: {audio_path}")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAudio"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "title": episode_title,
        "performer": "Frontier Pulse Agent",
        "caption": "🎧 Episodio semanal de Frontier Pulse",
    }

    print(f"[*] Uploading audio file to Telegram ({audio_path.name})...")
    try:
        with open(audio_path, "rb") as audio_file:
            files = {"audio": (audio_path.name, audio_file, "audio/mpeg")}
            response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            msg_id = res_data.get("result", {}).get("message_id")

        print("[+] Telegram audio episode published successfully!")
        return msg_id
    except requests.exceptions.RequestException as e:
        sanitized_err = sanitize_error_message(str(e))
        print(f"[!] Failed to send Telegram audio: {sanitized_err}")
        return None


def send_telegram_photo(photo_path: Path, caption: str = "🎙 Nueva edición de Frontier Pulse") -> int | None:
    """Upload photo file to Telegram chat via Bot API. Returns the message_id on success, or None on failure."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    if not photo_path.exists():
        print(f"[!] Photo file not found for Telegram upload: {photo_path}")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "Markdown",
    }

    print(f"[*] Uploading cover image to Telegram ({photo_path.name})...")
    try:
        with open(photo_path, "rb") as photo_file:
            files = {"photo": (photo_path.name, photo_file, "image/jpeg")}
            response = requests.post(url, data=data, files=files, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            msg_id = res_data.get("result", {}).get("message_id")

        print("[+] Telegram cover image published successfully!")
        return msg_id
    except requests.exceptions.RequestException as e:
        sanitized_err = sanitize_error_message(str(e))
        print(f"[!] Failed to send Telegram photo: {sanitized_err}")
        return None


def publish_to_telegram(manifest: EditionManifest = None) -> bool:
    """Main function to format news summary and publish both message and MP3 audio to Telegram idempotently."""
    try:
        news_data = load_current_news()
    except Exception as e:
        print(f"[!] Error loading news data for Telegram: {e}")
        raise e

    edition_date = news_data.get("edition_date", "Reciente")

    # If no manifest is passed, load or create one for today's date
    if manifest is None:
        manifest = create_or_load_manifest(edition_date)

    # 1. Validation check for credentials
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        err_msg = "Telegram credentials (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID) are missing in environment configuration."
        print(f"\n[!] CREDENTIALS ERROR: {err_msg}")
        update_manifest_stage(manifest, "failed", error=err_msg)
        raise ValueError(err_msg)

    print(f"\n[*] Publishing weekly episode to Telegram (ID: {manifest.edition_id})...")

    # 2. Publish Text Message Summary (if not already delivered)
    if not manifest.delivery_state.text_delivered:
        msg_text = format_telegram_message(news_data)
        msg_id = send_telegram_message(msg_text)
        if msg_id is None:
            err_msg = "Failed to send text summary to Telegram."
            update_manifest_stage(manifest, "failed", error=err_msg)
            raise RuntimeError(err_msg)
        manifest.delivery_state.text_delivered = True
        manifest.delivery_state.telegram_message_id = msg_id
        save_manifest_atomic(manifest)
    else:
        print("[*] Telegram text summary already delivered. Skipping (idempotent).")

    # 2.5 Publish Cover Art Image (if exists and not already delivered)
    image_path_str = manifest.artifacts.get("cover_image")
    image_path = Path(image_path_str) if image_path_str else (get_edition_dir(edition_date) / "podcast_cover.jpg")
    if not image_path.exists():
        image_path = OUTPUT_DIR / "podcast_cover.jpg"

    if image_path.exists():
        if not manifest.delivery_state.image_delivered:
            msg_id = send_telegram_photo(
                photo_path=image_path,
                caption=f"🎨 *Arte de Portada de la Edición {edition_date}* — Diseñado dinámicamente y generado por Imagen 3."
            )
            if msg_id is not None:
                manifest.delivery_state.image_delivered = True
                manifest.delivery_state.telegram_image_message_id = msg_id
                save_manifest_atomic(manifest)
            else:
                print("[!] Warning: Failed to send Telegram cover art. Proceeding with other assets.")
        else:
            print("[*] Telegram cover art already delivered. Skipping (idempotent).")
    else:
        print("[*] No cover art image found to publish.")

    # 3. Publish Audio Episode MP3 (if not already delivered)
    if not manifest.delivery_state.audio_delivered:
        episode_title = f"Frontier Pulse — {edition_date}"
        
        # Determine actual audio path from manifest artifacts, or fallback to default
        audio_path_str = manifest.artifacts.get("audio_file")
        audio_path = Path(audio_path_str) if audio_path_str else (OUTPUT_DIR / f"frontier_pulse_episode_{edition_date}.mp3")
        if not audio_path.exists():
            # Try fallback generic name
            audio_path = OUTPUT_DIR / "frontier_pulse_episode.mp3"

        msg_id = send_telegram_audio(audio_path=audio_path, episode_title=episode_title)
        if msg_id is None:
            err_msg = "Failed to upload audio episode to Telegram."
            update_manifest_stage(manifest, "failed", error=err_msg)
            raise RuntimeError(err_msg)
        manifest.delivery_state.audio_delivered = True
        manifest.delivery_state.telegram_audio_message_id = msg_id
        save_manifest_atomic(manifest)
    else:
        print("[*] Telegram audio episode already delivered. Skipping (idempotent).")

    # Mark as completely delivered
    if manifest.delivery_state.text_delivered and manifest.delivery_state.audio_delivered:
        update_manifest_stage(manifest, "delivered")
        return True

    return False


if __name__ == "__main__":
    publish_to_telegram()
