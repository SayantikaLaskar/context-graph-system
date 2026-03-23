from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from zipfile import ZipFile


FILE_ID = "1UqaLbFaveV-3MEuiUrzKydhKmkeC1iAL"
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
ZIP_PATH = RAW_DIR / "dataset.zip"
EXTRACT_DIR = RAW_DIR / "extracted"


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
    with urllib.request.urlopen(url, timeout=90) as response:
        ZIP_PATH.write_bytes(response.read())
    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)
    with ZipFile(ZIP_PATH) as archive:
        archive.extractall(EXTRACT_DIR)
    print(f"Downloaded dataset to {ZIP_PATH}")
    print(f"Extracted dataset to {EXTRACT_DIR}")


if __name__ == "__main__":
    main()
