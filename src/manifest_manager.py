import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from src.config import get_edition_dir
from src.schemas import EditionManifest


def get_manifest_path(edition_date: str) -> Path:
    """Return the absolute path for the manifest file corresponding to an edition date."""
    return get_edition_dir(edition_date) / "manifest.json"


def load_manifest(edition_date: str) -> EditionManifest | None:
    """Load an existing EditionManifest from disk. Returns None if it does not exist."""
    path = get_manifest_path(edition_date)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return EditionManifest.model_validate(data)
    except Exception as e:
        print(f"[!] Warning: Failed to load manifest at {path.name}: {e}")
        return None


def create_or_load_manifest(edition_date: str) -> EditionManifest:
    """Load an existing manifest, or initialize a new one with 'created' status if none exists."""
    manifest = load_manifest(edition_date)
    if manifest is None:
        manifest = EditionManifest(
            edition_id=edition_date,
            edition_date=edition_date,
            status="created"
        )
        save_manifest_atomic(manifest)
    return manifest


def save_manifest_atomic(manifest: EditionManifest) -> None:
    """Save the manifest to disk atomically to prevent data corruption during process interruption."""
    path = get_manifest_path(manifest.edition_date)
    temp_dir = path.parent
    
    # Dump manifest model to dict
    # Since datetime fields are serialized nicely to ISO-8601 strings by pydantic json dump
    manifest_data = json.loads(manifest.model_dump_json())
    
    # Write to a secure temporary file first, then atomically rename it
    fd, temp_file_path_str = tempfile.mkstemp(dir=temp_dir, prefix=f".manifest_{manifest.edition_date}_", suffix=".tmp")
    temp_file_path = Path(temp_file_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=2)
        # Atomic replacement of the target file
        os.replace(temp_file_path, path)
    except Exception as e:
        if temp_file_path.exists():
            temp_file_path.unlink()
        print(f"[!] Error: Atomic manifest write failed: {e}")
        raise e


def update_manifest_stage(manifest: EditionManifest, stage: str, artifacts: dict = None, error: str = None) -> None:
    """Update the status of a manifest, recording successful stages, failures, and generated artifacts."""
    valid_stages = ["created", "researched", "scripted", "audio_ready", "delivered", "completed", "failed"]
    
    manifest.updated_at = datetime.now(timezone.utc)
    
    if stage == "failed":
        # Keep current status or transition to failed
        manifest.failed_stage = manifest.status
        manifest.status = "failed"
        manifest.error_message = error or "Unknown failure"
    else:
        if stage not in valid_stages:
            raise ValueError(f"Invalid stage name: {stage}")
        manifest.status = stage
        manifest.last_successful_stage = stage
        manifest.failed_stage = None
        manifest.error_message = None
        
    if artifacts:
        # Merge dicts
        manifest.artifacts.update(artifacts)
        
    save_manifest_atomic(manifest)
    print(f"[*] Manifest '{manifest.edition_date}' updated to status '{manifest.status}'")
