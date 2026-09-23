"""Safe service client for academic-memory retrieval before any LLM call."""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("ai-agents-engine.academic_memory")


class AcademicMemoryClient:
    def __init__(self, base_url: str | None = None, service_key: str | None = None):
        self.base_url = (base_url or os.getenv("ACADEMIC_MEMORY_API_URL", "")).rstrip("/")
        self.service_key = service_key or os.getenv("ACADEMIC_MEMORY_AGENT_SERVICE_KEY", "")

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.service_key)

    def retrieve(self, *, organization_id: str, classroom_id: str, query: str) -> list[dict]:
        if not self.enabled or not query.strip():
            return []
        params = urlencode({"organization_id": organization_id, "classroom_id": classroom_id, "q": query, "limit": 1})
        request = Request(f"{self.base_url}/academic-memory/internal/retrieve?{params}", headers={"X-Agent-Service-Key": self.service_key})
        try:
            with urlopen(request, timeout=3) as response:  # nosec B310: URL is deployment-controlled environment configuration
                data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, list) else []
        except Exception as exc:  # retrieval is optional; LLM fallback remains available
            logger.warning("academic_memory_retrieval_failed error=%s", type(exc).__name__)
            return []
