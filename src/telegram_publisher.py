import json
import time
import requests
from pathlib import Path
from src.config import (
    INPUT_DIR,
    OUTPUT_DIR,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    TELEGRAM_TIMEOUT,
    TELEGRAM_RETRIES,
    TELEGRAM_PROXY_URL,
    TELEGRAM_STRICT,
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

    msg = f"🎙 *Frontier Pulse* — Edition {edition_date}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if is_slow_week:
        msg += "☕ *Continuity Edition (Quiet Week)*\n"
        msg += "Frontier AI labs have maintained stable operations this week. Here are the key highlights:\n\n"

    for idx, item in enumerate(items, 1):
        title = escape_markdown_legacy(item.get("title", "Untitled"))
        category = escape_markdown_legacy(item.get("category", ""))
        takeaways = item.get("key_takeaways", [])

        msg += f"*{idx}. {title}*\n"
        if category:
            msg += f"🏷 _{category}_\n"

        for takeaway in takeaways:
            escaped_takeaway = escape_markdown_legacy(takeaway)
            msg += f"• {escaped_takeaway}\n"
        msg += "\n"

    msg += "🎧 *Listen to the complete Spanish podcast episode in the audio attached below.*"
    return msg


def _get_request_proxies() -> dict | None:
    """Return proxies dictionary if proxy URL is configured."""
    if TELEGRAM_PROXY_URL:
        return {"http": TELEGRAM_PROXY_URL, "https": TELEGRAM_PROXY_URL}
    return None


def send_telegram_message(message_text: str) -> int | None:
    """Send text message to Telegram chat via Bot API with retry. Returns the message_id on success, or None on failure."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[!] TELEGRAM NOT CONFIGURED:")
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env.")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    proxies = _get_request_proxies()

    for attempt in range(1, TELEGRAM_RETRIES + 1):
        try:
            response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT, proxies=proxies)
            response.raise_for_status()
            res_data = response.json()
            msg_id = res_data.get("result", {}).get("message_id")
            print("[+] Telegram text summary sent successfully!")
            return msg_id
        except requests.exceptions.RequestException as e:
            sanitized_err = sanitize_error_message(str(e))
            print(f"[!] Telegram message attempt {attempt}/{TELEGRAM_RETRIES} failed: {sanitized_err}")
            if attempt < TELEGRAM_RETRIES:
                time.sleep(2 * attempt)

    return None


def send_telegram_audio(audio_path: Path = None, episode_title: str = "Frontier Pulse Episode") -> int | None:
    """Upload audio MP3 file to Telegram chat via Bot API with retry. Returns the message_id on success, or None on failure."""
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
        "caption": "🎧 Weekly Frontier Pulse Spanish Episode",
    }
    proxies = _get_request_proxies()

    print(f"[*] Uploading audio file to Telegram ({audio_path.name})...")
    for attempt in range(1, TELEGRAM_RETRIES + 1):
        try:
            with open(audio_path, "rb") as audio_file:
                files = {"audio": (audio_path.name, audio_file, "audio/mpeg")}
                response = requests.post(url, data=data, files=files, timeout=max(60, TELEGRAM_TIMEOUT), proxies=proxies)
                response.raise_for_status()
                res_data = response.json()
                msg_id = res_data.get("result", {}).get("message_id")

            print("[+] Telegram audio episode published successfully!")
            return msg_id
        except requests.exceptions.RequestException as e:
            sanitized_err = sanitize_error_message(str(e))
            print(f"[!] Telegram audio attempt {attempt}/{TELEGRAM_RETRIES} failed: {sanitized_err}")
            if attempt < TELEGRAM_RETRIES:
                time.sleep(2 * attempt)

    return None


def send_telegram_photo(photo_path: Path, caption: str = "🎙 New Frontier Pulse Edition") -> int | None:
    """Upload photo file to Telegram chat via Bot API with retry. Returns the message_id on success, or None on failure."""
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
    proxies = _get_request_proxies()

    print(f"[*] Uploading cover image to Telegram ({photo_path.name})...")
    for attempt in range(1, TELEGRAM_RETRIES + 1):
        try:
            with open(photo_path, "rb") as photo_file:
                files = {"photo": (photo_path.name, photo_file, "image/jpeg")}
                response = requests.post(url, data=data, files=files, timeout=max(60, TELEGRAM_TIMEOUT), proxies=proxies)
                response.raise_for_status()
                res_data = response.json()
                msg_id = res_data.get("result", {}).get("message_id")

            print("[+] Telegram cover image published successfully!")
            return msg_id
        except requests.exceptions.RequestException as e:
            sanitized_err = sanitize_error_message(str(e))
            print(f"[!] Telegram photo attempt {attempt}/{TELEGRAM_RETRIES} failed: {sanitized_err}")
            if attempt < TELEGRAM_RETRIES:
                time.sleep(2 * attempt)

    return None


def send_telegram_media_group(
    photo_paths: list[Path],
    caption: str = "🎨 *Frontier Pulse Visual Cards*"
) -> list[int] | None:
    """Upload multiple photos as an album (media group) to Telegram chat via Bot API.
    
    Returns list of message IDs on success, or None on failure.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    valid_paths = [p for p in photo_paths if p.exists()]
    if not valid_paths:
        print("[!] No valid photo files found for Telegram media group upload.")
        return None

    if len(valid_paths) == 1:
        msg_id = send_telegram_photo(valid_paths[0], caption=caption)
        return [msg_id] if msg_id else None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    proxies = _get_request_proxies()

    media_array = []
    for idx, path in enumerate(valid_paths):
        item = {
            "type": "photo",
            "media": f"attach://photo_{idx}",
        }
        if idx == 0:
            item["caption"] = caption
            item["parse_mode"] = "Markdown"
        media_array.append(item)

    print(f"[*] Uploading {len(valid_paths)} visual cards to Telegram as media group album...")
    for attempt in range(1, TELEGRAM_RETRIES + 1):
        file_handles = []
        try:
            files = {}
            for idx, path in enumerate(valid_paths):
                fh = open(path, "rb")
                file_handles.append(fh)
                files[f"photo_{idx}"] = (path.name, fh, "image/png")

            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "media": json.dumps(media_array),
            }

            response = requests.post(
                url,
                data=data,
                files=files,
                timeout=max(60, TELEGRAM_TIMEOUT),
                proxies=proxies
            )
            response.raise_for_status()
            res_data = response.json()
            results = res_data.get("result", [])
            msg_ids = [r.get("message_id") for r in results if "message_id" in r]
            print(f"[+] Telegram media group ({len(msg_ids)} cards) published successfully!")
            return msg_ids
        except requests.exceptions.RequestException as e:
            sanitized_err = sanitize_error_message(str(e))
            print(f"[!] Telegram media group attempt {attempt}/{TELEGRAM_RETRIES} failed: {sanitized_err}")
            if attempt < TELEGRAM_RETRIES:
                time.sleep(2 * attempt)
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    return None


def publish_to_telegram(manifest: EditionManifest = None) -> bool:
    """Main function to format news summary and publish message, visual cards, and MP3 audio to Telegram idempotently."""
    try:
        news_data = load_current_news()
    except Exception as e:
        print(f"[!] Error loading news data for Telegram: {e}")
        raise e

    edition_date = news_data.get("edition_date", "Recent")

    # If no manifest is passed, load or create one for today's date
    if manifest is None:
        manifest = create_or_load_manifest(edition_date)

    # 0. Check if Telegram publishing is disabled (e.g. for local test environments)
    if not TELEGRAM_ENABLED:
        print("\n[*] Telegram publishing is disabled (TELEGRAM_ENABLED=false / local test mode).")
        print(f"[+] All podcast artifacts for edition {edition_date} are verified in the output directory.")
        return True

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
            err_msg = "Failed to send text summary to Telegram (network timeout/firewall block)."
            if TELEGRAM_STRICT:
                update_manifest_stage(manifest, "failed", error=err_msg)
                raise RuntimeError(err_msg)
            else:
                print(f"[!] Warning: {err_msg} Skipping Telegram delivery in non-strict mode.")
                return False
        manifest.delivery_state.text_delivered = True
        manifest.delivery_state.telegram_message_id = msg_id
        save_manifest_atomic(manifest)
    else:
        print("[*] Telegram text summary already delivered. Skipping (idempotent).")

    # 2.5 Publish Visual Cards (Media Group / Album) (if exists and not already delivered)
    cards_to_send: list[Path] = []
    raw_visual_assets = manifest.artifacts.get("visual_assets")
    if raw_visual_assets and isinstance(raw_visual_assets, list):
        for p_str in raw_visual_assets:
            p = Path(p_str)
            if p.exists() and p not in cards_to_send:
                cards_to_send.append(p)

    if not cards_to_send:
        # Fallback: check cover_image or scan edition directory
        image_path_str = manifest.artifacts.get("cover_image")
        if image_path_str and Path(image_path_str).exists():
            cards_to_send.append(Path(image_path_str))
        else:
            edition_dir = get_edition_dir(edition_date)
            found_cards = sorted(list(edition_dir.glob("episode-*-*.png")))
            if found_cards:
                cards_to_send.extend(found_cards)

    if cards_to_send:
        if not manifest.delivery_state.image_delivered:
            msg_ids = send_telegram_media_group(
                photo_paths=cards_to_send,
                caption=f"🎨 *Frontier Pulse — Visual Cards ({edition_date})*"
            )
            if msg_ids:
                manifest.delivery_state.image_delivered = True
                manifest.delivery_state.telegram_image_message_id = msg_ids[0]
                save_manifest_atomic(manifest)
            else:
                print("[!] Warning: Failed to send Telegram visual cards. Proceeding with other assets.")
        else:
            print("[*] Telegram visual cards already delivered. Skipping (idempotent).")
    else:
        print("[*] No visual card images found to publish.")

    # 3. Publish Audio Episode MP3 (if not already delivered)
    if not manifest.delivery_state.audio_delivered:
        episode_title = f"Frontier Pulse — {edition_date}"
        
        # Determine actual audio path from manifest artifacts, or fallback to default
        audio_path_str = manifest.artifacts.get("audio_file")
        audio_path = Path(audio_path_str) if audio_path_str else (OUTPUT_DIR / f"frontier_pulse_episode_{edition_date}.mp3")
        if not audio_path.exists():
            audio_path = OUTPUT_DIR / "frontier_pulse_episode.mp3"

        msg_id = send_telegram_audio(audio_path=audio_path, episode_title=episode_title)
        if msg_id is None:
            err_msg = "Failed to upload audio episode to Telegram (network timeout/firewall block)."
            if TELEGRAM_STRICT:
                update_manifest_stage(manifest, "failed", error=err_msg)
                raise RuntimeError(err_msg)
            else:
                print(f"[!] Warning: {err_msg} Skipping Telegram delivery in non-strict mode.")
                return False
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
