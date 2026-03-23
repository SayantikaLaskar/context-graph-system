from __future__ import annotations

import json
from typing import Any

import httpx

from .config import settings


class OptionalLLMPlanner:
    def __init__(self) -> None:
        self.enabled = settings.llm_enabled

    def plan(self, question: str, schema_context: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        system_prompt = (
            "You generate read-only SQL plans for a SAP order-to-cash analytics assistant. "
            "Return JSON only with keys: mode, sql, answer_hint. "
            "Use exactly one SQL statement, and it must start with SELECT or WITH. "
            "Use only the tables and columns described in the schema. "
            "If the question is out of domain, return {\"mode\": \"reject\"}."
        )
        user_prompt = json.dumps({"question": question, "schema": schema_context}, indent=2)

        headers = {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=45) as client:
                response = client.post(settings.llm_api_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return None
