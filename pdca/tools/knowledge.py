"""Knowledge tool — RAG security knowledge lookup (B13)."""

from __future__ import annotations

import requests
from langchain_core.tools import tool

from pdca.config import settings
from pdca.observability.logger import get_logger
from pdca.tools.registry import REGISTRY

logger = get_logger(__name__)


@tool
def lookup_security_knowledge(query: str, mode: str = "both") -> dict:
    """Tra cứu tri thức bảo mật từ 2 nguồn:
    - 'maturity': Lộ trình bảo mật, Phase 1/2/3, rủi ro chiến lược.
    - 'technical': Chi tiết kỹ thuật của Prowler, cách fix lỗi.
    - 'both': Lấy cả hai.
    Dùng tool này khi người dùng hỏi 'Tại sao', 'Rủi ro là gì' hoặc 'Sửa thế nào'.
    """
    url = f"{settings.rag_api_url}/v1/retrieve/checks"
    try:
        resp = requests.post(
            url,
            json={"query": query, "mode": mode, "top_k": 2},
            timeout=settings.rag_timeout_s,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"success": False, "error": f"RAG returned {resp.status_code}"}
    except Exception as e:
        logger.warning("Knowledge API call failed", extra={"error": str(e)})
        return {"success": False, "error": str(e)}


REGISTRY.register(lookup_security_knowledge, category="knowledge")
