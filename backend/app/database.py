from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .config import DB_PATH, METADATA_PATH, PROCESSED_ROOT, RAW_DATA_ROOT
from .domain import ENTITY_CONFIG, camel_to_snake, normalize_identifier


NUMERIC_HINTS = ("amount", "quantity", "weight")
NORMALIZED_ID_COLUMNS = {
    "sales_order_item",
    "reference_sd_document_item",
    "delivery_document_item",
    "billing_document_item",
    "accounting_document_item",
    "schedule_line",
}


class DataRepository:
    def __init__(
        self,
        db_path: Path = DB_PATH,
        metadata_path: Path = METADATA_PATH,
        raw_data_root: Path = RAW_DATA_ROOT,
    ) -> None:
        self.db_path = db_path
        self.metadata_path = metadata_path
        self.raw_data_root = raw_data_root

    def ensure_initialized(self, force: bool = False) -> None:
        PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
        if force or not self.is_initialized():
            self._build_database()

    def is_initialized(self) -> bool:
        return self.db_path.exists() and self.metadata_path.exists()

    def get_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.get_connection() as connection:
            cursor = connection.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def load_metadata(self) -> dict[str, Any]:
        if not self.is_initialized():
            self.ensure_initialized()
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def _build_database(self) -> None:
        if not self.raw_data_root.exists():
            raise FileNotFoundError(
                f"Dataset not found at {self.raw_data_root}. Download and extract the assignment data first."
            )

        if self.db_path.exists():
            self.db_path.unlink()

        metadata: dict[str, Any] = {"tables": {}, "entities": {}}

        with self.get_connection() as connection:
            for table_dir in sorted(path for path in self.raw_data_root.iterdir() if path.is_dir()):
                dataframe = self._load_table(table_dir)
                dataframe.to_sql(table_dir.name, connection, if_exists="replace", index=False)
                self._create_indexes(connection, table_dir.name, dataframe.columns.tolist())
                metadata["tables"][table_dir.name] = {
                    "rows": int(len(dataframe)),
                    "columns": dataframe.columns.tolist(),
                }
            connection.commit()

        for entity_type, config in ENTITY_CONFIG.items():
            table_meta = metadata["tables"].get(config["table"], {})
            metadata["entities"][entity_type] = {
                "label": config["label"],
                "table": config["table"],
                "rows": table_meta.get("rows", 0),
                "columns": table_meta.get("columns", []),
            }

        self.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def _load_table(self, table_dir: Path) -> pd.DataFrame:
        parts = sorted(table_dir.glob("*.jsonl"))
        if not parts:
            raise FileNotFoundError(f"No JSONL files found in {table_dir}")

        frames = [pd.read_json(path, lines=True) for path in parts]
        dataframe = pd.concat(frames, ignore_index=True)
        dataframe.columns = [camel_to_snake(column) for column in dataframe.columns]
        dataframe = self._augment_columns(dataframe)
        return dataframe.where(pd.notna(dataframe), None)

    def _augment_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        for column in list(dataframe.columns):
            if any(hint in column for hint in NUMERIC_HINTS):
                try:
                    dataframe[column] = pd.to_numeric(dataframe[column])
                except (TypeError, ValueError):
                    pass

            if column in NORMALIZED_ID_COLUMNS:
                dataframe[f"normalized_{column}"] = dataframe[column].map(normalize_identifier)

            dataframe[column] = dataframe[column].map(self._normalize_scalar)

        if {"sales_order", "sales_order_item"}.issubset(dataframe.columns):
            dataframe["sales_order_item_key"] = (
                dataframe["sales_order"].astype(str) + ":" + dataframe["sales_order_item"].astype(str)
            )

        if {"delivery_document", "delivery_document_item"}.issubset(dataframe.columns):
            dataframe["delivery_item_key"] = (
                dataframe["delivery_document"].astype(str) + ":" + dataframe["delivery_document_item"].astype(str)
            )

        if {"billing_document", "billing_document_item"}.issubset(dataframe.columns):
            dataframe["billing_item_key"] = (
                dataframe["billing_document"].astype(str) + ":" + dataframe["billing_document_item"].astype(str)
            )

        if {"accounting_document", "accounting_document_item", "company_code", "fiscal_year"}.issubset(dataframe.columns):
            dataframe["journal_entry_key"] = (
                dataframe["company_code"].astype(str)
                + ":"
                + dataframe["fiscal_year"].astype(str)
                + ":"
                + dataframe["accounting_document"].astype(str)
                + ":"
                + dataframe["accounting_document_item"].astype(str)
            )

        if {"clearing_accounting_document", "accounting_document", "accounting_document_item"}.issubset(dataframe.columns):
            dataframe["payment_key"] = (
                dataframe["clearing_accounting_document"].astype(str)
                + ":"
                + dataframe["accounting_document"].astype(str)
                + ":"
                + dataframe["accounting_document_item"].astype(str)
            )

        return dataframe

    def _normalize_scalar(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return value

    def _create_indexes(self, connection: sqlite3.Connection, table_name: str, columns: list[str]) -> None:
        index_candidates = [
            "sales_order",
            "delivery_document",
            "billing_document",
            "accounting_document",
            "reference_document",
            "reference_sd_document",
            "material",
            "business_partner",
            "customer",
            "plant",
            "product",
        ]

        for column in index_candidates:
            if column in columns:
                connection.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{column} ON {table_name} ({column})"
                )
