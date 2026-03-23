from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.database import DataRepository


def main() -> None:
    repository = DataRepository()
    repository.ensure_initialized(force=True)
    metadata = repository.load_metadata()
    print(
        f"Prepared dataset with {len(metadata['tables'])} tables and {len(metadata['entities'])} graph entity types."
    )


if __name__ == "__main__":
    main()
