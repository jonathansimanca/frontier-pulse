import shutil
from pathlib import Path

def clean_workspace():
    # Paths to clear
    output_dir = Path("output")
    current_news = Path("input/current_news.json")

    print("[*] Cleaning generated files for a fresh execution...")

    # Delete current_news.json
    if current_news.exists():
        try:
            current_news.unlink()
            print("[-] Deleted: input/current_news.json")
        except Exception as e:
            print(f"[!] Error deleting input/current_news.json: {e}")

    # Clear output directory contents
    if output_dir.exists():
        for child in output_dir.iterdir():
            try:
                if child.is_file():
                    child.unlink()
                    print(f"[-] Deleted file: {child}")
                elif child.is_dir():
                    shutil.rmtree(child)
                    print(f"[-] Deleted directory: {child}")
            except Exception as e:
                print(f"[!] Error deleting {child}: {e}")

    print("[+] Workspace is perfectly clean and ready for a fresh run!")

if __name__ == "__main__":
    clean_workspace()
