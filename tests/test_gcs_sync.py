import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from src.config import INPUT_DIR, OUTPUT_DIR
from src.gcs_sync import download_from_gcs, upload_to_gcs, get_gcs_client

@pytest.fixture
def mock_storage_client():
    """Fixture to mock Google Cloud Storage Client and Bucket operations."""
    with patch("src.gcs_sync.storage.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        
        yield mock_client, mock_bucket

def test_get_gcs_client_not_configured():
    """Test that GCS client returns None when GCS_BUCKET_NAME env var is not set."""
    with patch("src.gcs_sync.GCS_BUCKET_NAME", ""):
        client = get_gcs_client()
        assert client is None

def test_get_gcs_client_configured(mock_storage_client):
    """Test that GCS client initializes when GCS_BUCKET_NAME env var is set."""
    mock_client, _ = mock_storage_client
    with patch("src.gcs_sync.GCS_BUCKET_NAME", "my-test-bucket"):
        client = get_gcs_client()
        assert client is not None

def test_download_from_gcs_skips_when_empty_env():
    """Test that download_from_gcs gracefully skips execution when no bucket is set."""
    with patch("src.gcs_sync.GCS_BUCKET_NAME", ""), \
         patch("src.gcs_sync.get_gcs_client", return_value=None) as mock_get_client:
        download_from_gcs()
        mock_get_client.assert_called_once()

def test_download_from_gcs_syncs_paths(mock_storage_client, tmp_path):
    """Test that download_from_gcs lists and downloads blobs to correct local paths."""
    mock_client, mock_bucket = mock_storage_client
    
    # Mock inputs and history blobs
    blob_input = MagicMock()
    blob_input.name = "input/sample_news.json"
    
    blob_history = MagicMock()
    blob_history.name = "output/history/history_2026-08-04.json"
    
    blob_manifest = MagicMock()
    blob_manifest.name = "output/editions/2026-08-05/manifest.json"
    
    # Configure mock_client.list_blobs to return specific values based on the prefix argument
    def list_blobs_side_effect(bucket_name, prefix=None):
        if prefix == "input/":
            return [blob_input]
        elif prefix == "output/history/":
            return [blob_history]
        elif prefix == "output/editions/":
            return [blob_manifest]
        return []
        
    mock_client.list_blobs.side_effect = list_blobs_side_effect
    
    # Patch INPUT_DIR and OUTPUT_DIR to point to our test temp directory
    tmp_input_dir = tmp_path / "input"
    tmp_output_dir = tmp_path / "output"
    
    with patch("src.gcs_sync.GCS_BUCKET_NAME", "my-test-bucket"), \
         patch("src.gcs_sync.INPUT_DIR", tmp_input_dir), \
         patch("src.gcs_sync.OUTPUT_DIR", tmp_output_dir):
         
        download_from_gcs()
        
        # Verify blob download calls
        blob_input.download_to_filename.assert_called_once_with(str(tmp_input_dir / "sample_news.json"))
        blob_history.download_to_filename.assert_called_once_with(str((tmp_output_dir / "history" / "history_2026-08-04.json")))
        blob_manifest.download_to_filename.assert_called_once_with(str(tmp_output_dir / "editions" / "2026-08-05" / "manifest.json"))

def test_upload_to_gcs_syncs_paths(mock_storage_client, tmp_path):
    """Test that upload_to_gcs walks output directory and uploads nested files to correct blob paths."""
    mock_client, mock_bucket = mock_storage_client
    
    # Create test outputs structure in temp path
    tmp_output_dir = tmp_path / "output"
    history_file = tmp_output_dir / "history" / "history_2026-08-05.json"
    edition_file = tmp_output_dir / "editions" / "2026-08-05" / "podcast_episode.mp3"
    
    history_file.parent.mkdir(parents=True, exist_ok=True)
    edition_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(history_file, "w") as f:
        f.write("{}")
    with open(edition_file, "wb") as f:
        f.write(b"mp3_data")
        
    mock_blob_history = MagicMock()
    mock_blob_edition = MagicMock()
    
    # Configure mock_bucket.blob side effect
    def blob_side_effect(blob_name):
        if blob_name == "output/history/history_2026-08-05.json":
            return mock_blob_history
        elif blob_name == "output/editions/2026-08-05/podcast_episode.mp3":
            return mock_blob_edition
        return MagicMock()
        
    mock_bucket.blob.side_effect = blob_side_effect
    
    with patch("src.gcs_sync.GCS_BUCKET_NAME", "my-test-bucket"), \
         patch("src.gcs_sync.OUTPUT_DIR", tmp_output_dir):
         
        upload_to_gcs()
        
        # Verify that both files walk recursively and are uploaded with the correct blob prefix
        mock_blob_history.upload_from_filename.assert_called_once_with(str(history_file))
        mock_blob_edition.upload_from_filename.assert_called_once_with(str(edition_file))
