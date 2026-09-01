from types import SimpleNamespace

import src.main as main


def test_completed_edition_with_valid_assets_stays_idempotent(monkeypatch, tmp_path):
    manifest = SimpleNamespace(status="completed", artifacts={"visual_assets_manifest": "assets.json"})
    monkeypatch.setattr(main, "validate_four_card_asset_set", lambda *_: (True, "Valid 4-card asset set."))

    should_skip, reason = main.should_skip_completed_edition(manifest, tmp_path, 3)

    assert should_skip is True
    assert reason == "Valid 4-card asset set."


def test_completed_edition_with_missing_assets_reopens_at_audio_ready(monkeypatch, tmp_path):
    manifest = SimpleNamespace(status="completed", artifacts={"visual_assets_manifest": "assets.json"})
    updates = []
    monkeypatch.setattr(main, "validate_four_card_asset_set", lambda *_: (False, "Asset file missing on disk."))
    monkeypatch.setattr(main, "update_manifest_stage", lambda item, stage: updates.append((item, stage)))

    should_skip, reason = main.should_skip_completed_edition(manifest, tmp_path, 3)

    assert should_skip is False
    assert reason == "Asset file missing on disk."
    assert updates == [(manifest, "audio_ready")]
