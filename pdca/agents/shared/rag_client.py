"""
RAGClient — Shared HTTP client cho RAG API
=============================================
Cung cấp interface thống nhất cho tất cả agents gọi RAG API.
Bao gồm: retry, timeout, error handling, graceful fallback.

Tham chiếu: Integration_Implementation_Plan.md — SLICE-0.2

Sử dụng:
    from pdca.agents.shared.rag_client import RAGClient
    client = RAGClient(base_url="http://localhost:8001")

    if client.is_healthy():
        result = client.build_context(consumer="risk", check_ids=["s3_bucket_public_access"])
"""

import logging
from typing import Any, Dict, List, Literal, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class RAGClient:
    """
    Shared HTTP client gọi RAG API (FastAPI, port 8001).

    - Retry tự động cho server errors (5xx) và timeout.
    - Không raise exception ra ngoài — return None khi fail.
    - Thread-safe (requests.Session).
    """

    def __init__(
        self,
        base_url: str = None,
        timeout: float = 10.0,
        max_retries: int = 1,
    ):
        if base_url is None:
            from pdca.config import RAG_API_URL
            base_url = RAG_API_URL

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Tạo Session với retry adapter
        self._session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        logger.debug("RAGClient initialized: base_url=%s, timeout=%.1f, max_retries=%d",
                      self.base_url, self.timeout, max_retries)

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """
        GET /ready — Kiểm tra RAG service có sẵn sàng không.

        Returns:
            True nếu status 200 và status field là "ready".
            False nếu timeout/error hoặc service chưa ready.
        """
        # Try /ready first, fall back to /health
        for endpoint in ("/ready", "/health"):
            url = f"{self.base_url}{endpoint}"
            try:
                resp = self._session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    # /ready returns {"status":"ready"}, /health returns {"status":"ok"}
                    is_ready = data.get("status") in ("ready", "ok")
                    logger.debug("RAG health check (%s): status=%s, ready=%s", endpoint, data.get("status"), is_ready)
                    return is_ready
                logger.warning("RAG health check failed (%s): HTTP %d", endpoint, resp.status_code)
            except Exception:
                continue
        logger.warning("RAG health check: all endpoints failed")
        return False

    # ------------------------------------------------------------------
    # Retrieve Checks
    # ------------------------------------------------------------------

    def retrieve_checks(
        self,
        query: Optional[str] = None,
        check_id: Optional[str] = None,
        service: Optional[str] = None,
        top_k: int = 5,
        retrieval_mode: Literal["lexical", "vector", "hybrid"] = "hybrid",
        debug: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        POST /v1/retrieve/checks — Truy xuất Prowler security checks.

        Returns:
            {"results": [...], "meta": {...}} hoặc None khi fail.
        """
        url = f"{self.base_url}/v1/retrieve/checks"
        payload: Dict[str, Any] = {
            "top_k": top_k,
            "retrieval_mode": retrieval_mode,
            "debug": debug,
        }
        if query is not None:
            payload["query"] = query
        if check_id is not None:
            payload["check_id"] = check_id
        if service is not None:
            payload["service"] = service

        return self._post(url, payload, "retrieve_checks")

    # ------------------------------------------------------------------
    # Retrieve Maturity
    # ------------------------------------------------------------------

    def retrieve_maturity(
        self,
        query: Optional[str] = None,
        capability_id: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 5,
        retrieval_mode: Literal["lexical", "vector", "hybrid"] = "hybrid",
        debug: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        POST /v1/retrieve/maturity — Truy xuất maturity capabilities.

        Returns:
            {"results": [...], "meta": {...}} hoặc None khi fail.
        """
        url = f"{self.base_url}/v1/retrieve/maturity"
        payload: Dict[str, Any] = {
            "top_k": top_k,
            "retrieval_mode": retrieval_mode,
            "debug": debug,
        }
        if query is not None:
            payload["query"] = query
        if capability_id is not None:
            payload["capability_id"] = capability_id
        if domain is not None:
            payload["domain"] = domain

        return self._post(url, payload, "retrieve_maturity")

    # ------------------------------------------------------------------
    # Build Context (method CHÍNH cho agents)
    # ------------------------------------------------------------------

    def build_context(
        self,
        consumer: Literal["planning", "risk", "report"],
        query: Optional[str] = None,
        check_ids: Optional[List[str]] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
        service: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 5,
        retrieval_mode: Literal["lexical", "vector", "hybrid"] = "hybrid",
        include_mappings: bool = True,
        include_maturity: bool = True,
        max_context_items: int = 8,
        max_chars_per_item: int = 600,
        debug: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        POST /v1/context/build — Tạo context bundle cho agent.

        Đây là method CHÍNH. Response chứa bundle tương ứng consumer:
        - consumer="planning" → payload.planning_bundle
        - consumer="risk"     → payload.risk_bundle
        - consumer="report"   → payload.report_bundle

        Returns:
            Full response data dict (chứa "payload", "diagnostics") hoặc None khi fail.
            Agent truy cập: result["payload"]["{consumer}_bundle"]
        """
        url = f"{self.base_url}/v1/context/build"
        payload: Dict[str, Any] = {
            "consumer": consumer,
            "top_k": top_k,
            "retrieval_mode": retrieval_mode,
            "include_mappings": include_mappings,
            "include_maturity": include_maturity,
            "max_context_items": max_context_items,
            "max_chars_per_item": max_chars_per_item,
            "debug": debug,
        }
        if query is not None:
            payload["query"] = query
        if check_ids is not None:
            payload["check_ids"] = check_ids
        if findings is not None:
            payload["findings"] = findings
        if service is not None:
            payload["service"] = service
        if domain is not None:
            payload["domain"] = domain

        result = self._post(url, payload, "build_context", include_meta=True)

        if result is not None:
            # Validate response có đúng bundle cho consumer
            bundle_key = f"{consumer}_bundle"
            payload_data = result.get("payload", {})
            if bundle_key not in payload_data:
                logger.warning(
                    "build_context: response missing '%s' in payload. Keys: %s",
                    bundle_key, list(payload_data.keys())
                )
            else:
                logger.debug("build_context: '%s' found with keys: %s",
                             bundle_key, list(payload_data[bundle_key].keys()))

        return result

    # ------------------------------------------------------------------
    # Resolve Mapping
    # ------------------------------------------------------------------

    def resolve_mapping(
        self,
        check_id: str,
        service: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        POST /v1/resolve/mapping — Resolve check → capability mapping.

        Returns:
            {"mapping": {...}, "candidates": [...]} hoặc None khi fail.
        """
        url = f"{self.base_url}/v1/resolve/mapping"
        payload: Dict[str, Any] = {"check_id": check_id}
        if service is not None:
            payload["service"] = service

        return self._post(url, payload, "resolve_mapping")

    # ------------------------------------------------------------------
    # Internal: POST helper
    # ------------------------------------------------------------------

    def _post(self, url: str, payload: Dict[str, Any], method_name: str,
              include_meta: bool = False) -> Optional[Dict[str, Any]]:
        """
        Internal helper — POST request với error handling.

        Args:
            include_meta: Nếu True, inject envelope "meta" vào result["_meta"].
                          Dùng cho build_context() để truy cập confidence level.

        Returns:
            Parsed "data" field từ ResponseEnvelope, hoặc None khi fail.
        """
        logger.debug("%s: POST %s payload=%s", method_name, url, payload)

        # App-level retry for transient ConnectionError. urllib3 Retry inside
        # HTTPAdapter doesn't always cover bare ConnectionError on Windows,
        # so we wrap the call with an explicit retry loop (linear backoff).
        _conn_attempts = 3
        _last_err: Optional[Exception] = None
        resp = None
        for _attempt in range(1, _conn_attempts + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=self.timeout)
                break
            except requests.exceptions.ConnectionError as e:
                _last_err = e
                if _attempt < _conn_attempts:
                    _sleep = 0.5 * _attempt
                    logger.warning(
                        "%s: connection error on attempt %d/%d, retrying in %.1fs...",
                        method_name, _attempt, _conn_attempts, _sleep,
                    )
                    import time as _t
                    _t.sleep(_sleep)
                    continue
                logger.warning(
                    "%s: connection error after %d attempts calling %s: %s",
                    method_name, _conn_attempts, url, e,
                )
                return None
            except requests.exceptions.Timeout:
                logger.warning("%s: timeout after %.1fs calling %s",
                                method_name, self.timeout, url)
                return None

        if resp is None:
            return None

        try:
            resp.raise_for_status()

            envelope = resp.json()

            # ResponseEnvelope structure: {request_id, status, data, meta, errors}
            status = envelope.get("status")
            if status == "error":
                errors = envelope.get("errors", [])
                # Include both code and message so callers can distinguish
                # CHECK_CONTEXT_MISSING / MAPPING_CONTEXT_MISSING /
                # MATURITY_CONTEXT_MISSING etc. without enabling debug mode.
                detailed = [
                    f"{e.get('code', 'UNKNOWN')}: {e.get('message', 'unknown')}"
                    for e in errors
                ]
                logger.warning(
                    "%s: API returned error status. Errors: %s. Request payload keys: %s",
                    method_name, detailed, list(payload.keys()),
                )
                return None

            if status == "partial":
                errors = envelope.get("errors", [])
                logger.warning("%s: API returned partial status, errors: %s", method_name,
                               [e.get("message") for e in errors])

            # Return "data" field (contains payload, diagnostics, etc.)
            data = envelope.get("data")
            if data is None:
                logger.warning("%s: response has no 'data' field", method_name)
                return None

            # Inject envelope meta if requested (SLICE-1.2: confidence access)
            if include_meta and isinstance(data, dict):
                data["_meta"] = envelope.get("meta", {})

            logger.debug("%s: success (status=%s)", method_name, status)
            return data

        except requests.exceptions.HTTPError as e:
            logger.warning("%s: HTTP error %s calling %s", method_name, e.response.status_code if e.response else "?", url)
            return None
        except Exception as e:
            logger.warning("%s: unexpected error: %s", method_name, e)
            return None
