"""ReportContextService — orchestrates Q1+Q2+Q3 for the report agent.

Q1: existing ContextService.build() — check findings + capability themes (legacy).
Q2: MaturityService.search() filtered by domain → CapabilityTheme.
Q3: Direct lookup in raw prowler_checks corpus → RemediationGuide.

All three run concurrently via asyncio.gather. Graceful degradation:
- If Q2 or Q3 fail, Q1 result is still returned with confidence="medium".
- If Q1 fails, bundle is empty with confidence="low".
"""
from __future__ import annotations

import ast
import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.models import (
    CapabilityTheme,
    Citation,
    ContextBuildRequest,
    ReportCapability,
    ReportCapabilityDetail,
    ReportContextBundle,
    ReportContextRequest,
    ReportFinding,
    RemediationGuide,
    RemediationStep,
    RetrieveMaturityRequest,
)
from app.services.context_service import ContextService
from app.services.maturity_service import MaturityService

logger = logging.getLogger(__name__)

_PROWLER_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "normalized" / "prowler_checks.json"

# Descriptive queries per domain — "s3" alone is too short for BM25
_DOMAIN_QUERIES: Dict[str, str] = {
    "s3": "S3 bucket public access block encryption data protection",
    "iam": "IAM identity access management least privilege MFA root account",
    "ec2": "EC2 instance security group network access metadata service",
    "vpc": "VPC network segmentation flow logs subnet security",
    "cloudtrail": "CloudTrail audit API calls logging monitoring",
    "cloudwatch": "CloudWatch alarm billing anomaly detection monitoring",
    "kms": "KMS encryption at rest key management CMK",
    "guardduty": "GuardDuty threat detection malware security findings",
    "rds": "RDS database encryption backup security",
    "cloudfront": "CloudFront CDN HTTPS TLS origin access",
    "waf": "WAF web application firewall managed rules protection",
    "config": "AWS Config compliance rule configuration recorder",
    "securityhub": "Security Hub security posture findings standards",
    "backup": "data backup recovery disaster recovery",
    "organizations": "AWS Organizations SCP region restriction guardrails",
    "resilience_hub": "resilience posture availability recovery",
    "general": "AWS security best practices controls maturity",
}

_EFFORT_MAP = {
    "CRITICAL": "high",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}


class ReportContextService:
    """Aggregate Q1+Q2+Q3 retrieval for the report agent."""

    def __init__(
        self,
        context_service: ContextService,
        maturity_service: MaturityService,
    ) -> None:
        self._ctx = context_service
        self._mat = maturity_service
        self._prowler_cache: Optional[Dict[str, dict]] = None
        self._cache_lock = threading.Lock()
        # Simple in-memory result cache: key -> (bundle, ts)
        self._result_cache: Dict[str, tuple] = {}
        self._result_cache_ttl = 60

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def build(self, req: ReportContextRequest) -> ReportContextBundle:
        cache_key = self._cache_key(req)
        cached = self._get_cached(cache_key)
        if cached is not None:
            cached.diagnostics["cache_hit"] = True
            return cached

        t0 = time.perf_counter()

        q1_task = asyncio.create_task(self._run_q1(req))
        q3_task = asyncio.create_task(self._run_q3(req)) if req.include_q3 else None

        tasks = [q1_task]
        if q3_task:
            tasks.append(q3_task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        q1_result = results[0]
        q3_result = results[1] if q3_task else []

        if isinstance(q1_result, Exception):
            logger.error("Q1 failed: %s", q1_result)
            q1_bundle: Dict[str, Any] = {}
            confidence = "low"
        else:
            q1_bundle = q1_result
            confidence = "high"

        if isinstance(q3_result, Exception):
            logger.warning("Q3 failed (degraded): %s", q3_result)
            q3_result = []
            confidence = "medium" if confidence == "high" else confidence

        q2_result = (
            self._themes_from_capability_details(q1_bundle, req.domains)
            if req.include_q2
            else []
        )

        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        bundle = ReportContextBundle(
            check_findings=q1_bundle.get("check_findings", []),
            control_themes=q1_bundle.get("control_themes", []),
            capability_details=q1_bundle.get("capability_details", []),
            recommended_practices=q1_bundle.get("recommended_practices", []),
            primary_topics=q1_bundle.get("primary_topics", []),
            capability_themes=q2_result if isinstance(q2_result, list) else [],
            remediations=q3_result if isinstance(q3_result, list) else [],
            confidence=confidence,
            diagnostics={
                "total_latency_ms": total_ms,
                "cache_hit": False,
                "q2_source": "resolved_capability_details",
            },
        )
        self._set_cached(cache_key, bundle)
        return bundle

    # ------------------------------------------------------------------
    # Q1 — existing ContextService
    # ------------------------------------------------------------------

    async def _run_q1(self, req: ReportContextRequest) -> Dict[str, Any]:
        ctx_req = ContextBuildRequest(
            consumer="report",
            check_ids=req.check_ids,
            top_k=req.top_k_check,
        )
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, self._ctx.build, ctx_req)

        bundle = resp.data.payload.report_bundle
        if bundle is None:
            return {}

        return {
            "check_findings": [f.model_dump() for f in bundle.key_findings],
            "control_themes": [t.model_dump() for t in bundle.control_themes],
            "capability_details": [d.model_dump() for d in bundle.capability_details],
            "recommended_practices": list(bundle.recommended_practices),
            "primary_topics": list(bundle.primary_topics),
        }

    # ------------------------------------------------------------------
    # Q2 — capability themes by domain
    # ------------------------------------------------------------------

    async def _run_q2(self, req: ReportContextRequest) -> List[CapabilityTheme]:
        domains = req.domains or ["general"]
        loop = asyncio.get_event_loop()
        themes: List[CapabilityTheme] = []
        seen_domains: set = set()

        for domain in domains[:5]:
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            # Build descriptive query so BM25 can match; bare domain name is
            # too short and gets filtered as a stopword in the index.
            query = _DOMAIN_QUERIES.get(domain, f"{domain} security best practices")
            mat_req = RetrieveMaturityRequest(
                query=query,
                top_k=req.top_k_capability,
            )
            resp = await loop.run_in_executor(None, self._mat.search, mat_req)
            results = resp.data.get("results", []) if resp.status != "error" else []
            if not results:
                continue
            theme = self._build_capability_theme(domain, results)
            if theme:
                themes.append(theme)

        return themes

    def _themes_from_capability_details(
        self,
        q1_bundle: Dict[str, Any],
        requested_domains: List[str],
    ) -> List[CapabilityTheme]:
        """Build Q2 themes only from capabilities resolved by check mappings.

        The previous implementation queried broad domain strings such as
        "s3" and then concatenated maturity corpus fields. That made the
        trace noisy and could pull unrelated Macie/GuardDuty/CloudTrail text
        into an S3 run. This path only uses Q1 capability_details, which are
        already tied to the actual check IDs selected for the report.
        """
        details = q1_bundle.get("capability_details") or []
        if not details:
            return []

        requested = {str(d).strip().lower() for d in requested_domains if str(d).strip()}
        themes: List[CapabilityTheme] = []
        seen: set[str] = set()

        for d in details:
            if not isinstance(d, dict):
                continue
            cap_id = str(d.get("capability_id") or "").strip()
            name = str(d.get("capability_name") or cap_id or "").strip()
            domain = str(d.get("domain") or "").strip().lower()
            if requested and domain and domain not in requested:
                continue
            key = cap_id or name
            if not key or key in seen:
                continue
            seen.add(key)

            summary = self._trim_sentence(d.get("summary"), 220)
            risk = self._trim_sentence(d.get("risk_explanation"), 220)
            recommendation = self._trim_sentence(d.get("recommendation"), 180)
            narrative_parts = [p for p in (summary, risk, recommendation) if p]
            if not narrative_parts:
                continue

            url = str(d.get("url") or "").strip()
            if not url:
                continue
            citations = [Citation(source=name, url=url)]
            themes.append(
                CapabilityTheme(
                    domain=domain or (next(iter(requested), "general") if requested else "general"),
                    narrative=" ".join(narrative_parts[:2]),
                    common_pitfalls=[],
                    baselines=[],
                    citations=citations,
                )
            )
            if len(themes) >= 5:
                break

        return themes

    @staticmethod
    def _trim_sentence(value: Any, max_len: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= max_len:
            return text
        cut = text.rfind(". ", 0, max_len)
        if cut < max_len - 80:
            cut = text.rfind(" ", 0, max_len)
        return (text[:cut].rstrip() if cut > 0 else text[:max_len].rstrip()) + "…"

    def _build_capability_theme(
        self, domain: str, results: List[Dict[str, Any]]
    ) -> Optional[CapabilityTheme]:
        narratives: List[str] = []
        pitfalls: List[str] = []
        baselines: List[str] = []
        citations: List[Citation] = []

        for r in results[:5]:
            meta = r.get("metadata", {}) if isinstance(r, dict) else {}
            # Use risk_explanation or guidance as narrative (summary field is often empty in index)
            narrative_raw = (
                meta.get("risk_explanation") or meta.get("guidance")
                or r.get("risk_explanation") or r.get("guidance")
                or meta.get("summary") or r.get("summary") or r.get("short_text", "")
            )
            risk = meta.get("risk_explanation") or r.get("risk_explanation", "")
            how_to = meta.get("how_to_check") or r.get("how_to_check", "")
            practices = meta.get("recommended_practices") or r.get("recommended_practices") or []
            url = meta.get("source_uri") or r.get("source_uri", "")
            name = meta.get("capability_name") or r.get("capability_name", "")

            if narrative_raw:
                narratives.append(narrative_raw[:300])
            if risk and risk not in narratives:
                pitfalls.append(risk[:200])
            if how_to:
                pitfalls.append(how_to[:150])
            if isinstance(practices, list):
                baselines.extend(p for p in practices[:2] if p)
            if url and name:
                citations.append(Citation(source=name, url=url))

        if not narratives:
            return None

        return CapabilityTheme(
            domain=domain,
            narrative=" ".join(narratives[:2]),
            common_pitfalls=pitfalls[:5],
            baselines=baselines[:5],
            citations=citations[:5],
        )

    # ------------------------------------------------------------------
    # Q3 — remediation steps by check_id
    # ------------------------------------------------------------------

    async def _run_q3(self, req: ReportContextRequest) -> List[RemediationGuide]:
        corpus = self._load_prowler_corpus()
        guides: List[RemediationGuide] = []
        for check_id in req.check_ids[: req.top_k_remediation * 3]:
            guide = self._build_remediation_guide(
                check_id=check_id,
                severity=req.severity_map.get(check_id),
                corpus=corpus,
            )
            if guide:
                guides.append(guide)
            if len(guides) >= req.top_k_remediation:
                break
        return guides

    def _load_prowler_corpus(self) -> Dict[str, dict]:
        with self._cache_lock:
            if self._prowler_cache is not None:
                return self._prowler_cache
            if not _PROWLER_JSON.exists():
                logger.warning("prowler_checks.json not found at %s", _PROWLER_JSON)
                self._prowler_cache = {}
                return {}
            raw = json.loads(_PROWLER_JSON.read_text(encoding="utf-8"))
            index: Dict[str, dict] = {}
            for rec in raw:
                cid = (rec.get("CheckID") or rec.get("check_id") or "").strip().lower().replace("-", "_")
                if cid:
                    index[cid] = rec
            self._prowler_cache = index
            logger.info("Loaded %d prowler checks into remediation cache", len(index))
            return index

    def _build_remediation_guide(
        self,
        check_id: str,
        severity: Optional[str],
        corpus: Dict[str, dict],
    ) -> Optional[RemediationGuide]:
        norm_id = check_id.strip().lower().replace("-", "_")
        raw = corpus.get(norm_id)
        if not raw:
            return None

        remediation_blob = raw.get("Remediation") or raw.get("remediation") or ""
        steps: List[RemediationStep] = []
        order = 1

        if remediation_blob:
            parsed = self._parse_remediation_blob(remediation_blob)
            if parsed:
                for step_type, key in [("cli", "CLI"), ("iac", "NativeIaC"), ("iac", "Terraform"), ("other", "Other")]:
                    snippet = parsed.get(key, "").strip()
                    if snippet:
                        steps.append(RemediationStep(
                            order=order,
                            type=step_type,
                            snippet=snippet[:1000],
                        ))
                        order += 1

        # Fallback to narrative recommendation if no structured steps
        if not steps:
            narrative = (raw.get("remediation_recommendation") or raw.get("Remediation") or "").strip()
            if narrative and not narrative.startswith("{") and not narrative.startswith("'"):
                steps.append(RemediationStep(order=1, type="other", snippet=narrative[:500]))

        url = raw.get("remediation_url") or ""
        citations = [Citation(source=check_id, url=url)] if url else []

        return RemediationGuide(
            check_id=norm_id,
            steps=steps,
            effort=_EFFORT_MAP.get(severity or "", "medium"),
            citations=citations,
        )

    @staticmethod
    def _parse_remediation_blob(blob: str) -> Optional[Dict[str, str]]:
        if not blob or not isinstance(blob, str):
            return None
        blob = blob.strip()
        if blob.startswith("{") or blob.startswith("'"):
            try:
                result = ast.literal_eval(blob)
                if isinstance(result, dict):
                    return {str(k): str(v) for k, v in result.items()}
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, req: ReportContextRequest) -> str:
        ids = ",".join(sorted(req.check_ids))
        domains = ",".join(sorted(req.domains))
        return f"{ids}|{domains}|{req.include_q2}|{req.include_q3}"

    def _get_cached(self, key: str) -> Optional[ReportContextBundle]:
        entry = self._result_cache.get(key)
        if entry and (time.time() - entry[1]) < self._result_cache_ttl:
            return entry[0]
        return None

    def _set_cached(self, key: str, bundle: ReportContextBundle) -> None:
        self._result_cache[key] = (bundle, time.time())
