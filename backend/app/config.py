from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT_DIR / "data"
RAW_DATA_ROOT = DATA_ROOT / "raw" / "extracted" / "sap-o2c-data"
PROCESSED_ROOT = DATA_ROOT / "processed"
FRONTEND_ROOT = ROOT_DIR / "frontend"
DB_PATH = PROCESSED_ROOT / "o2c_graph.sqlite"
METADATA_PATH = PROCESSED_ROOT / "dataset_metadata.json"


@dataclass(slots=True)
class Settings:
    app_name: str = "Context Graph System"
    llm_provider: str = os.getenv("LLM_PROVIDER", "").strip().lower()
    llm_model: str = os.getenv("LLM_MODEL", "").strip()
    llm_api_key: str = os.getenv("LLM_API_KEY", "").strip()
    llm_api_url: str = os.getenv("LLM_API_URL", "").strip()

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_url and self.llm_model)


settings = Settings()
