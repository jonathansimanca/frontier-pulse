import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from src.ia_news_researcher import research_ai_news
from src.script_generator import generate_podcast_script
from src.audio_generator import load_spanish_script, synthesize_speech
from src.image_generator import generate_podcast_cover
from src.telegram_publisher import publish_to_telegram

from src.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    OUTPUT_DIR,
    INPUT_DIR,
    get_edition_dir,
)
from src.manifest_manager import (
    create_or_load_manifest,
    update_manifest_stage,
    save_manifest_atomic,
)


def run_pipeline():
    """Run the complete end-to-end Frontier Pulse pipeline with atomic checkpoint resumes and idempotent delivery."""
    print("=" * 65)
    print("   FRONTIER PULSE - AUTOMATED PODCAST GENERATOR")
    print("=" * 65)

    # Step 0: Load manifest and perform startup validation
    edition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    manifest = create_or_load_manifest(edition_date)

    # Startup validation: missing required delivery credentials fails the production run
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        err_msg = "Telegram credentials (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID) are missing. Failing startup validation."
        print(f"\n[!] STARTUP VALIDATION ERROR: {err_msg}")
        update_manifest_stage(manifest, "failed", error=err_msg)
        sys.exit(1)

    # Idempotent skip: if already delivered, exit successfully
    if manifest.status == "delivered":
        print(f"\n[+] Edition {edition_date} already successfully delivered. skipping execution (idempotent).")
        print("=" * 65)
        sys.exit(0)

    try:
        # Step 1: Dynamic AI Web Research with Deduplication & Priority Tracking
        print("\n--- STEP 1: Dynamic AI Web Research (Gemini Search Grounding) ---")
        # Resume check
        news_file_str = manifest.artifacts.get("news_file")
        has_news = news_file_str and Path(news_file_str).exists()
        
        if manifest.status in ["researched", "scripted", "audio_ready", "failed"] and has_news and manifest.last_successful_stage not in [None, "created"]:
            print(f"[+] Resuming: News already researched. Loading artifact from: {news_file_str}")
            with open(news_file_str, "r", encoding="utf-8") as f:
                news_data = json.load(f)
        else:
            news_data = research_ai_news(edition_date)
            edition_dir = get_edition_dir(edition_date)
            news_file = edition_dir / "edition.json"
            candidates_file = edition_dir / "candidates.json"
            update_manifest_stage(
                manifest,
                "researched",
                artifacts={
                    "news_file": str(news_file.resolve()),
                    "candidates_file": str(candidates_file.resolve()),
                }
            )

        # Step 1.5: Editorial Quality Gate Validation
        print("\n--- STEP 1.5: Editorial Quality Gate (Quality Control) ---")
        from src.quality_gate import validate_edition_quality
        quality_report = validate_edition_quality(news_data)
        
        # Save quality report in artifacts
        edition_dir = get_edition_dir(edition_date)
        report_file = edition_dir / "quality_report.json"
        manifest.artifacts["quality_report"] = str(report_file.resolve())
        save_manifest_atomic(manifest)
        
        if not quality_report.passed:
            print("\n[!] EDITORIAL QUALITY GATE FAILED:")
            for reason in quality_report.reasons_for_failure:
                print(f"    - {reason}")
            # Register failure in manifest
            update_manifest_stage(
                manifest,
                "failed",
                error_message="Editorial quality gate failed: " + "; ".join(quality_report.reasons_for_failure)
            )
            # Prevent automatic generation by raising an error
            raise ValueError("Editorial quality gate failed. Correct current_news.json selection or candidates and try again.")

        # Step 2: Generate Spanish & English Transcripts
        print("\n--- STEP 2: Generating Spanish and English Transcripts ---")
        es_script_str = manifest.artifacts.get("es_script_file")
        en_script_str = manifest.artifacts.get("en_script_file")
        has_scripts = es_script_str and en_script_str and Path(es_script_str).exists() and Path(en_script_str).exists()
        
        if manifest.status in ["scripted", "audio_ready", "failed"] and has_scripts and manifest.last_successful_stage not in [None, "created", "researched"]:
            print(f"[+] Resuming: Scripts already generated.")
            print(f"    Spanish Script: {es_script_str}")
            print(f"    English Script: {en_script_str}")
            es_script_path = Path(es_script_str)
            en_script_path = Path(en_script_str)
        else:
            es_script_path, en_script_path = generate_podcast_script()
            update_manifest_stage(
                manifest,
                "scripted",
                artifacts={
                    "es_script_file": str(es_script_path.resolve()),
                    "en_script_file": str(en_script_path.resolve()),
                }
            )

        # Step 3: Synthesize Latin American Spanish Audio
        print("\n--- STEP 3: Synthesizing Latin American Spanish Audio ---")
        audio_file_str = manifest.artifacts.get("audio_file")
        has_audio = audio_file_str and Path(audio_file_str).exists()
        
        if manifest.status in ["audio_ready", "failed"] and has_audio and manifest.last_successful_stage not in [None, "created", "researched", "scripted"]:
            print(f"[+] Resuming: Audio already synthesized: {audio_file_str}")
            audio_path = Path(audio_file_str)
        else:
            script_text = load_spanish_script(es_script_path)
            edition_dir = get_edition_dir(edition_date)
            custom_audio_path = edition_dir / "podcast_episode.mp3"
            audio_path = synthesize_speech(script_text, output_audio_path=custom_audio_path)
            update_manifest_stage(
                manifest,
                "audio_ready",
                artifacts={
                    "audio_file": str(audio_path.resolve())
                }
            )

        # Step 3.5: Generate Podcast Cover Image (Nano Banana)
        print("\n--- STEP 3.5: Generating Podcast Cover Art ---")
        cover_file_str = manifest.artifacts.get("cover_image")
        has_cover = cover_file_str and Path(cover_file_str).exists()
        
        if has_cover and manifest.last_successful_stage not in [None, "created", "researched", "scripted", "audio_ready"]:
            print(f"[+] Resuming: Cover image already generated: {cover_file_str}")
            cover_path = Path(cover_file_str)
        else:
            cover_path = generate_podcast_cover(news_data, edition_date)
            if cover_path:
                manifest.artifacts["cover_image"] = str(cover_path.resolve())
                save_manifest_atomic(manifest)
            else:
                print("[!] Warning: Cover image generation failed, continuing pipeline without cover image.")

        # Step 4: Publish to Telegram (Idempotent delivery)
        print("\n--- STEP 4: Publishing Episode to Telegram ---")
        published = publish_to_telegram(manifest)

        print("\n" + "=" * 65)
        print("   EPISODE GENERATION COMPLETE!")
        print(f"   Date:              {edition_date}")
        print(f"   Spanish Script:    {es_script_path}")
        print(f"   English Script:    {en_script_path}")
        print(f"   Audio MP3:        {audio_path}")
        print(f"   Telegram Delivery: {'Delivered' if published else 'Skipped/Pending'}")
        print("=" * 65)

    except BaseException as e:
        # If it's a clean SystemExit, just raise/exit without marking as failed
        if isinstance(e, SystemExit) and e.code == 0:
            raise e
            
        print(f"\n[!] PIPELINE EXECUTION FAILED: {e}")
        update_manifest_stage(manifest, "failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    run_pipeline()
