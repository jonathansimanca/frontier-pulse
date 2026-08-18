import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.schemas import EditionManifest, DeliveryState
from src.manifest_manager import (
    create_or_load_manifest,
    load_manifest,
    save_manifest_atomic,
    update_manifest_stage,
    get_manifest_path,
)
from src.telegram_publisher import publish_to_telegram


@pytest.fixture(autouse=True)
def clean_test_manifests(tmp_path):
    """Fixture to redirect manifest and output directories to a temporary folder for clean testing."""
    with patch("src.manifest_manager.get_edition_dir", return_value=tmp_path), \
         patch("src.telegram_publisher.get_edition_dir", return_value=tmp_path), \
         patch("src.telegram_publisher.OUTPUT_DIR", tmp_path):
        yield


def test_manifest_creation_and_atomic_save():
    """Verify that a manifest can be created, saved atomically, and loaded back successfully."""
    manifest = create_or_load_manifest("2026-08-10")
    assert manifest.edition_date == "2026-08-10"
    assert manifest.status == "created"
    assert manifest.delivery_state.text_delivered is False
    assert manifest.delivery_state.audio_delivered is False

    # Check file exists
    path = get_manifest_path("2026-08-10")
    assert path.exists()

    # Modify and save
    manifest.delivery_state.text_delivered = True
    save_manifest_atomic(manifest)

    # Reload and verify
    reloaded = load_manifest("2026-08-10")
    assert reloaded is not None
    assert reloaded.delivery_state.text_delivered is True
    assert reloaded.delivery_state.audio_delivered is False


def test_manifest_stage_transitions():
    """Verify that updating the manifest stage updates state, artifacts, and errors correctly."""
    manifest = create_or_load_manifest("2026-08-11")
    
    # Transition to researched
    update_manifest_stage(manifest, "researched", artifacts={"news_file": "/path/to/news.json"})
    assert manifest.status == "researched"
    assert manifest.last_successful_stage == "researched"
    assert manifest.artifacts.get("news_file") == "/path/to/news.json"
    assert manifest.failed_stage is None

    # Transition to failed
    update_manifest_stage(manifest, "failed", error="TTS synthesis timed out")
    assert manifest.status == "failed"
    assert manifest.failed_stage == "researched"
    assert manifest.error_message == "TTS synthesis timed out"
    assert manifest.last_successful_stage == "researched"  # Retained last valid stage

    # Transition back to successful scripted stage
    update_manifest_stage(manifest, "scripted", artifacts={"es_script_file": "/path/to/script.txt"})
    assert manifest.status == "scripted"
    assert manifest.last_successful_stage == "scripted"
    assert manifest.failed_stage is None
    assert manifest.error_message is None
    assert manifest.artifacts.get("es_script_file") == "/path/to/script.txt"


@patch("src.telegram_publisher.requests.post")
@patch("src.telegram_publisher.TELEGRAM_BOT_TOKEN", "mock-token")
@patch("src.telegram_publisher.TELEGRAM_CHAT_ID", "mock-chat")
@patch("src.telegram_publisher.TELEGRAM_ENABLED", True)
@patch("src.telegram_publisher.TELEGRAM_STRICT", True)
@patch("src.telegram_publisher.TELEGRAM_RETRIES", 1)
def test_idempotent_telegram_delivery(mock_post, tmp_path):
    """Verify that Telegram publishing is fully idempotent and can resume/retry partially failed sends."""
    # Mock responses for text sendMessage and audio sendAudio
    mock_response_msg = MagicMock()
    mock_response_msg.json.return_value = {"ok": True, "result": {"message_id": 11111}}
    mock_response_msg.raise_for_status = MagicMock()

    mock_response_audio = MagicMock()
    mock_response_audio.json.return_value = {"ok": True, "result": {"message_id": 22222}}
    mock_response_audio.raise_for_status = MagicMock()

    # Sequence of post calls: text first, then audio
    mock_post.side_effect = [mock_response_msg, mock_response_audio]

    # Create dummy news and script files for the publisher to read
    dummy_news = {
        "edition_date": "2026-08-12",
        "title": "Edition 2026-08-12",
        "items": []
    }
    news_file = tmp_path / "current_news.json"
    with open(news_file, "w", encoding="utf-8") as f:
        json.dump(dummy_news, f)

    dummy_audio = tmp_path / "frontier_pulse_episode_2026-08-12.mp3"
    dummy_audio.write_bytes(b"dummy mp3 data")

    manifest = create_or_load_manifest("2026-08-12")
    manifest.status = "audio_ready"
    manifest.artifacts = {
        "news_file": str(news_file),
        "audio_file": str(dummy_audio)
    }
    save_manifest_atomic(manifest)

    # Patch inputs and configuration paths
    with patch("src.telegram_publisher.load_current_news", return_value=dummy_news):
        # First execution run (both text and audio need to be delivered)
        publish_to_telegram(manifest)
        
        # Check that both sent successfully and recorded IDs
        assert manifest.delivery_state.text_delivered is True
        assert manifest.delivery_state.audio_delivered is True
        assert manifest.delivery_state.telegram_message_id == 11111
        assert manifest.delivery_state.telegram_audio_message_id == 22222
        assert manifest.status == "delivered"
        assert mock_post.call_count == 2

        # Reset mock call history
        mock_post.reset_mock()

        # Second execution run (idempotent skip for everything!)
        publish_to_telegram(manifest)
        # Should not make any network requests!
        mock_post.assert_not_called()


@patch("src.telegram_publisher.requests.post")
@patch("src.telegram_publisher.TELEGRAM_BOT_TOKEN", "mock-token")
@patch("src.telegram_publisher.TELEGRAM_CHAT_ID", "mock-chat")
@patch("src.telegram_publisher.TELEGRAM_ENABLED", True)
@patch("src.telegram_publisher.TELEGRAM_STRICT", True)
@patch("src.telegram_publisher.TELEGRAM_RETRIES", 1)
def test_partial_telegram_delivery_failure_and_resume(mock_post, tmp_path):
    """Verify that if text succeeds but audio fails, a retry only sends the missing audio component."""
    # Mock responses: text sendMessage succeeds, audio sendAudio fails
    mock_response_msg = MagicMock()
    mock_response_msg.json.return_value = {"ok": True, "result": {"message_id": 11111}}
    mock_response_msg.raise_for_status = MagicMock()

    import requests
    mock_response_fail = MagicMock()
    mock_response_fail.raise_for_status.side_effect = requests.exceptions.HTTPError("Audio upload failed")

    # Sequence of post calls: text first, then audio fail
    mock_post.side_effect = [mock_response_msg, mock_response_fail]

    # Create dummy news and script files for the publisher to read
    dummy_news = {
        "edition_date": "2026-08-13",
        "title": "Edition 2026-08-13",
        "items": []
    }
    news_file = tmp_path / "current_news.json"
    with open(news_file, "w", encoding="utf-8") as f:
        json.dump(dummy_news, f)

    dummy_audio = tmp_path / "frontier_pulse_episode_2026-08-13.mp3"
    dummy_audio.write_bytes(b"dummy mp3 data")

    manifest = create_or_load_manifest("2026-08-13")
    manifest.status = "audio_ready"
    manifest.artifacts = {
        "news_file": str(news_file),
        "audio_file": str(dummy_audio)
    }
    save_manifest_atomic(manifest)

    # Patch inputs
    with patch("src.telegram_publisher.load_current_news", return_value=dummy_news):
        # Run first delivery attempt. This should fail on the audio step and raise an exception.
        with pytest.raises(Exception):
            publish_to_telegram(manifest)
        
        # Verify text was marked delivered, but audio was not, and status is "failed"
        assert manifest.delivery_state.text_delivered is True
        assert manifest.delivery_state.audio_delivered is False
        assert manifest.delivery_state.telegram_message_id == 11111
        assert manifest.status == "failed"
        assert manifest.failed_stage == "audio_ready"  # It failed during audio publishing

        # Now, fix the mock post for the next run so the audio succeeds
        mock_post.reset_mock()
        mock_response_audio_ok = MagicMock()
        mock_response_audio_ok.json.return_value = {"ok": True, "result": {"message_id": 33333}}
        mock_response_audio_ok.raise_for_status = MagicMock()
        mock_post.side_effect = [mock_response_audio_ok]

        # Run publish_to_telegram again to simulate a pipeline resume
        publish_to_telegram(manifest)

        # Only the missing audio should be sent!
        assert manifest.delivery_state.audio_delivered is True
        assert manifest.delivery_state.telegram_audio_message_id == 33333
        assert manifest.status == "delivered"
        # The mock post should have only been called once (for sendAudio, not sendMessage)
        assert mock_post.call_count == 1


def test_calculate_edition_window():
    """Verify that edition window calculations are explicit, correct, and timezone-aligned."""
    from src.ia_news_researcher import calculate_edition_window
    
    # Check regular Monday date
    start, end = calculate_edition_window("2026-08-03")
    assert start == "2026-07-27T00:00:00-05:00"
    assert end == "2026-08-03T23:59:59-05:00"
    
    # Check transition across months/leap years (e.g. March 1st, 2024 - leap year!)
    start, end = calculate_edition_window("2024-03-01")
    assert start == "2024-02-23T00:00:00-05:00"
    assert end == "2024-03-01T23:59:59-05:00"


def test_telegram_formatting_and_escaping():
    """Verify that characters active in Telegram legacy Markdown are correctly escaped (FP-017)."""
    from src.telegram_publisher import escape_markdown_legacy, format_telegram_message

    # Test individual escaping
    assert escape_markdown_legacy("OpenAI's GPT_5 release") == "OpenAI's GPT\\_5 release"
    assert escape_markdown_legacy("A *bold* announcement") == "A \\*bold\\* announcement"
    assert escape_markdown_legacy("Code `print()` and brackets [A]") == "Code \\`print()\\` and brackets \\[A]"

    # Test full message formatting with active markdown symbols in news content
    news_data = {
        "edition_date": "2026-08-03",
        "is_slow_week": False,
        "items": [
            {
                "title": "Claude_3.5_Opus *Leaked*",
                "category": "Models_Update",
                "key_takeaways": [
                    "Takeaway _one_",
                    "Takeaway [two] *bold*"
                ]
            }
        ]
    }
    msg = format_telegram_message(news_data)

    # Core message structure should remain intact
    assert "🎙 *Frontier Pulse* — Edition 2026-08-03" in msg
    # Injected news title, category, and takeaways should be escaped to prevent Telegram parse errors
    assert "Claude\\_3.5\\_Opus \\*Leaked\\*" in msg
    assert "🏷 _Models\\_Update_" in msg
    assert "• Takeaway \\_one\\_" in msg
    assert "• Takeaway \\[two] \\*bold\\*" in msg



def test_telegram_token_redaction():
    """Verify that exceptions and logs containing the Telegram Bot Token are redacted (FP-017)."""
    from src.telegram_publisher import sanitize_error_message, TELEGRAM_BOT_TOKEN
    
    if not TELEGRAM_BOT_TOKEN:
        # Patch a fake token for test execution
        with patch("src.telegram_publisher.TELEGRAM_BOT_TOKEN", "123456:ABC-def123"):
            err_msg = "HTTP 401: Unauthorized request to http://telegram.org/bot123456:ABC-def123/sendMessage"
            sanitized = sanitize_error_message(err_msg)
            assert "123456:ABC-def123" not in sanitized
            assert "<REDACTED_TELEGRAM_TOKEN>" in sanitized
    else:
        err_msg = f"HTTP 401: Unauthorized request to bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        sanitized = sanitize_error_message(err_msg)
        assert TELEGRAM_BOT_TOKEN not in sanitized
        assert "<REDACTED_TELEGRAM_TOKEN>" in sanitized


