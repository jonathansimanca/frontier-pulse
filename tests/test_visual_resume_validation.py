"""Tests for Visual Asset Manifest and Resume Validation in Frontier Pulse."""

import json
from pathlib import Path
from PIL import Image
import pytest

from src.visual_asset_generator import validate_four_card_asset_set
from src.visual_theme import CANVAS_WIDTH, CANVAS_HEIGHT


def create_dummy_png(path: Path, size=(CANVAS_WIDTH, CANVAS_HEIGHT)):
    """Helper to create a minimal valid PNG with exact dimensions."""
    img = Image.new("RGBA", size, (27, 23, 21, 255))
    img.save(path, format="PNG")


def test_resume_validation_missing_manifest_path(tmp_path):
    """Resume validation should fail if manifest path is None or does not exist."""
    is_valid, reason = validate_four_card_asset_set(None, tmp_path, 4)
    assert not is_valid
    assert "No manifest path" in reason

    missing_path = tmp_path / "non_existent.json"
    is_valid, reason = validate_four_card_asset_set(str(missing_path), tmp_path, 4)
    assert not is_valid
    assert "does not exist" in reason


def test_resume_validation_legacy_manifest_with_three_assets(tmp_path):
    """Resume validation should fail on legacy manifests with fewer than 4 assets."""
    manifest_data = {
        "episode_number": 4,
        "edition_date": "2026-08-18",
        "assets": [
            {
                "file": "episode-4-01-cover.png",
                "type": "cover",
                "display_order": 1,
                "suggested_screen_time_seconds": 3,
                "text": {
                    "series": "FRONTIER PULSE",
                    "format": "PODCAST",
                    "headline": "Cover Headline",
                    "metadata": "Ep 4",
                    "cta": "Play"
                }
            },
            {
                "file": "episode-4-02-insight-story-a.png",
                "type": "news_insight",
                "display_order": 2,
                "suggested_screen_time_seconds": 5,
                "text": {
                    "label": "IA",
                    "title": "Title A",
                    "key_fact": "Fact",
                    "why_it_matters": "Why",
                    "footer": "Foot"
                }
            },
            {
                "file": "episode-4-03-insight-story-b.png",
                "type": "news_insight",
                "display_order": 3,
                "suggested_screen_time_seconds": 5,
                "text": {
                    "label": "IA",
                    "title": "Title B",
                    "key_fact": "Fact",
                    "why_it_matters": "Why",
                    "footer": "Foot"
                }
            }
        ]
    }
    manifest_file = tmp_path / "episode-4-assets.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    is_valid, reason = validate_four_card_asset_set(str(manifest_file), tmp_path, 4)
    assert not is_valid
    assert "Manifest validation error" in reason or "assets" in reason


def test_resume_validation_four_assets_with_one_missing_file(tmp_path):
    """Resume validation should fail if 1 of the 4 card image files is missing on disk."""
    files = [
        "episode-4-01-cover.png",
        "episode-4-02-insight-test-a.png",
        "episode-4-03-insight-test-b.png",
        "episode-4-04-news-roundup.png"
    ]

    # Create only the first 3 files
    for fname in files[:3]:
        create_dummy_png(tmp_path / fname)

    manifest_data = {
        "episode_number": 4,
        "edition_date": "2026-08-18",
        "assets": [
            {
                "file": files[0],
                "type": "cover",
                "display_order": 1,
                "suggested_screen_time_seconds": 3,
                "text": {"series": "PULSE", "format": "FMT", "headline": "H", "metadata": "M", "cta": "C"}
            },
            {
                "file": files[1],
                "type": "news_insight",
                "display_order": 2,
                "suggested_screen_time_seconds": 5,
                "text": {"label": "L", "title": "T1", "key_fact": "F", "why_it_matters": "W", "footer": "F"}
            },
            {
                "file": files[2],
                "type": "news_insight",
                "display_order": 3,
                "suggested_screen_time_seconds": 5,
                "text": {"label": "L", "title": "T2", "key_fact": "F", "why_it_matters": "W", "footer": "F"}
            },
            {
                "file": files[3],
                "type": "news_roundup",
                "display_order": 4,
                "suggested_screen_time_seconds": 8,
                "text": {"label": "L", "headline": "H", "remaining_titles": ["R1"], "cta": "C", "footer": "F"}
            }
        ]
    }
    manifest_file = tmp_path / "episode-4-assets.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    is_valid, reason = validate_four_card_asset_set(str(manifest_file), tmp_path, 4)
    assert not is_valid
    assert "missing on disk" in reason or "episode-4-04-news-roundup.png" in reason


def test_resume_validation_invalid_dimensions(tmp_path):
    """Resume validation should fail if an image has invalid dimensions."""
    files = [
        "episode-4-01-cover.png",
        "episode-4-02-insight-test-a.png",
        "episode-4-03-insight-test-b.png",
        "episode-4-04-news-roundup.png"
    ]
    # Create files, with file 2 having wrong dimensions (800x800)
    create_dummy_png(tmp_path / files[0], (1080, 1350))
    create_dummy_png(tmp_path / files[1], (800, 800))
    create_dummy_png(tmp_path / files[2], (1080, 1350))
    create_dummy_png(tmp_path / files[3], (1080, 1350))

    manifest_data = {
        "episode_number": 4,
        "edition_date": "2026-08-18",
        "assets": [
            {
                "file": files[0],
                "type": "cover",
                "display_order": 1,
                "suggested_screen_time_seconds": 3,
                "text": {"series": "PULSE", "format": "FMT", "headline": "H", "metadata": "M", "cta": "C"}
            },
            {
                "file": files[1],
                "type": "news_insight",
                "display_order": 2,
                "suggested_screen_time_seconds": 5,
                "text": {"label": "L", "title": "T1", "key_fact": "F", "why_it_matters": "W", "footer": "F"}
            },
            {
                "file": files[2],
                "type": "news_insight",
                "display_order": 3,
                "suggested_screen_time_seconds": 5,
                "text": {"label": "L", "title": "T2", "key_fact": "F", "why_it_matters": "W", "footer": "F"}
            },
            {
                "file": files[3],
                "type": "news_roundup",
                "display_order": 4,
                "suggested_screen_time_seconds": 8,
                "text": {"label": "L", "headline": "H", "remaining_titles": ["R1"], "cta": "C", "footer": "F"}
            }
        ]
    }
    manifest_file = tmp_path / "episode-4-assets.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    is_valid, reason = validate_four_card_asset_set(str(manifest_file), tmp_path, 4)
    assert not is_valid
    assert "invalid dimensions" in reason


def test_resume_validation_valid_complete_manifest(tmp_path):
    """Resume validation should succeed when all 4 files are valid 1080x1350 PNGs and orders are [1, 2, 3, 4]."""
    files = [
        "episode-4-01-cover.png",
        "episode-4-02-insight-test-a.png",
        "episode-4-03-insight-test-b.png",
        "episode-4-04-news-roundup.png"
    ]
    for fname in files:
        create_dummy_png(tmp_path / fname, (1080, 1350))

    manifest_data = {
        "episode_number": 4,
        "edition_date": "2026-08-18",
        "assets": [
            {
                "file": files[0],
                "type": "cover",
                "display_order": 1,
                "suggested_screen_time_seconds": 3,
                "text": {"series": "PULSE", "format": "FMT", "headline": "H", "metadata": "M", "cta": "C"}
            },
            {
                "file": files[1],
                "type": "news_insight",
                "display_order": 2,
                "suggested_screen_time_seconds": 5,
                "text": {"label": "L", "title": "T1", "key_fact": "F", "why_it_matters": "W", "footer": "F"}
            },
            {
                "file": files[2],
                "type": "news_insight",
                "display_order": 3,
                "suggested_screen_time_seconds": 5,
                "text": {"label": "L", "title": "T2", "key_fact": "F", "why_it_matters": "W", "footer": "F"}
            },
            {
                "file": files[3],
                "type": "news_roundup",
                "display_order": 4,
                "suggested_screen_time_seconds": 8,
                "text": {"label": "L", "headline": "H", "remaining_titles": ["R1"], "cta": "C", "footer": "F"}
            }
        ]
    }
    manifest_file = tmp_path / "episode-4-assets.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    is_valid, reason = validate_four_card_asset_set(str(manifest_file), tmp_path, 4)
    assert is_valid
    assert "Valid 4-card asset set" in reason
