import os
from pathlib import Path
from google.cloud import storage

from src.config import INPUT_DIR, OUTPUT_DIR

# Retrieve bucket name from environment variable
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")

def get_gcs_client():
    """Retrieve GCS Client, returning None gracefully if unauthenticated or not configured."""
    if not GCS_BUCKET_NAME:
        return None
    try:
        return storage.Client()
    except Exception as e:
        print(f"[!] Warning: GCS Client initialization failed: {e}")
        return None

def download_from_gcs():
    """Download historical files, config inputs, and active manifest from GCS to local directories."""
    client = get_gcs_client()
    if not client:
        print("[*] GCS sync: Skipping download (GCS_BUCKET_NAME not set or unauthorized).")
        return

    print(f"[*] GCS sync: Synchronizing files from bucket '{GCS_BUCKET_NAME}' to local storage...")
    try:
        
        # Download input/ folder
        blobs_input = client.list_blobs(GCS_BUCKET_NAME, prefix="input/")
        for blob in blobs_input:
            if blob.name.endswith("/"):
                continue
            local_path = INPUT_DIR / blob.name[len("input/"):]
            local_path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(local_path))
            print(f"    - Synchronized: gs://{GCS_BUCKET_NAME}/{blob.name} -> {local_path}")
            
        # Download output/history/ folder
        blobs_history = client.list_blobs(GCS_BUCKET_NAME, prefix="output/history/")
        for blob in blobs_history:
            if blob.name.endswith("/"):
                continue
            local_path = (OUTPUT_DIR / "history") / blob.name[len("output/history/"):]
            local_path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(local_path))
            print(f"    - Synchronized: gs://{GCS_BUCKET_NAME}/{blob.name} -> {local_path}")

        # Download existing active manifest files (for checkpoint resume)
        blobs_editions = client.list_blobs(GCS_BUCKET_NAME, prefix="output/editions/")
        for blob in blobs_editions:
            if blob.name.endswith("manifest.json"):
                local_path = OUTPUT_DIR / blob.name[len("output/"):]
                local_path.parent.mkdir(parents=True, exist_ok=True)
                blob.download_to_filename(str(local_path))
                print(f"    - Synchronized active manifest: gs://{GCS_BUCKET_NAME}/{blob.name} -> {local_path}")

        print("[+] GCS sync: Download phase completed successfully.")
    except Exception as e:
        print(f"[!] Warning: GCS download synchronization failed: {e}")

def upload_to_gcs():
    """Upload newly generated edition artifacts and updated history metadata back to GCS."""
    client = get_gcs_client()
    if not client:
        print("[*] GCS sync: Skipping upload (GCS_BUCKET_NAME not set or unauthorized).")
        return

    print(f"[*] GCS sync: Uploading output data back to GCS bucket '{GCS_BUCKET_NAME}'...")
    try:
        bucket = client.bucket(GCS_BUCKET_NAME)
        
        # Walk recursively inside local OUTPUT_DIR to upload all nested files and folders
        uploaded_count = 0
        for root, dirs, files in os.walk(OUTPUT_DIR):
            for file in files:
                local_file_path = Path(root) / file
                relative_path = local_file_path.relative_to(OUTPUT_DIR)
                blob_name = f"output/{relative_path.as_posix()}"
                
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(str(local_file_path))
                print(f"    - Uploaded: {local_file_path} -> gs://{GCS_BUCKET_NAME}/{blob_name}")
                uploaded_count += 1

        print(f"[+] GCS sync: Upload phase completed successfully ({uploaded_count} files synchronized).")
    except Exception as e:
        print(f"[!] Warning: GCS upload synchronization failed: {e}")
