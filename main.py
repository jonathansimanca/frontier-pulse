import functions_framework
from src.gcs_sync import download_from_gcs, upload_to_gcs
from src.main import run_pipeline

@functions_framework.http
def run_edition_gcf(request):
    """GCP Cloud Run Function (Gen 2) HTTP trigger entrypoint.
    
    Coordinates the Sync-on-Start, Core Pipeline execution, and Sync-on-Success phases.
    """
    print("\n" + "=" * 65)
    print("   FRONTIER PULSE - GCP SERVERLESS HANDLER STARTED")
    print("=" * 65)
    
    # 1. Sync-on-Start: Download inputs and history metadata from GCS
    print("[*] PHASE 1: Sync-on-Start (GCS Download)...")
    try:
        download_from_gcs()
    except Exception as e:
        print(f"[!] Warning: Sync-on-Start failed: {e}")

    # 2. Core Execution: Run the fully robust automated pipeline
    print("\n[*] PHASE 2: Core Pipeline Execution...")
    pipeline_success = False
    try:
        run_pipeline()
        pipeline_success = True
        print("[+] Core pipeline finished successfully!")
    except SystemExit as se:
        # Catch sys.exit() calls from intermediate stages or startup validation
        if se.code == 0:
            pipeline_success = True
            print("[+] Core pipeline bypassed gracefully (e.g., idempotent skip).")
        else:
            print(f"[!] Warning: Pipeline exited with code {se.code}")
            pipeline_success = False
    except Exception as e:
        print(f"[!] Critical: Core pipeline crashed with error: {e}")
        pipeline_success = False

    # 3. Sync-on-Success: Upload all local outputs and updated manifests back to GCS
    print("\n[*] PHASE 3: Sync-on-Success (GCS Upload)...")
    try:
        upload_to_gcs()
    except Exception as e:
        print(f"[!] Warning: Sync-on-Success failed: {e}")

    print("\n" + "=" * 65)
    print("   FRONTIER PULSE - GCP SERVERLESS HANDLER FINISHED")
    print("=" * 65)

    if pipeline_success:
        return "Frontier Pulse weekly edition processed, delivered, and archived successfully.", 200
    else:
        return "Frontier Pulse pipeline failed during execution. Please review Cloud Logging logs.", 500
