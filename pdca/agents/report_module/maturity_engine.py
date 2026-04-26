"""
MaturityEngine — Scoring engine for AWS Security Maturity Assessment.

Loads maturity mappings and capabilities from normalized JSON files,
scores findings against the AWS Security Maturity Model, and computes
pre/post remediation deltas.
"""
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOMAIN_DISPLAY = {
    "data_protection": "Data Protection",
    "identity_access": "Identity & Access Management",
    "logging_monitoring": "Logging & Monitoring",
    "resilience": "Resilience",
    "network_security": "Network Security",
}

STAGE_LABELS = {
    "1 quickwins": "Quick Wins",
    "2 foundational": "Foundational",
    "3 efficient": "Efficient",
    "4 optimized": "Optimized",
}

STAGE_ORDER = ["1 quickwins", "2 foundational", "3 efficient", "4 optimized"]

# Weight matrix: (mapping_type, mapping_confidence) → weight
_MAPPING_WEIGHTS = {
    ("direct", "high"):    1.0,
    ("direct", "medium"):  0.8,
    ("direct", "low"):     0.6,
    ("related", "high"):   0.7,
    ("related", "medium"): 0.5,
    ("related", "low"):    0.3,
    ("weak", "high"):      0.3,
    ("weak", "medium"):    0.2,
    ("weak", "low"):       0.2,
}

# Thresholds
CAPABILITY_PASS_THRESHOLD = 50.0   # score >= 50% to count as "passing"
STAGE_COMPLETION_THRESHOLD = 0.70  # 70% of stage caps must pass


class MaturityEngine:
    """Score findings against the AWS Security Maturity Model."""

    def __init__(self, mappings_path: str, capabilities_path: str):
        self._mappings_raw = self._load_json(mappings_path, "maturity_mappings")
        self._capabilities_raw = self._load_json(capabilities_path, "maturity_capabilities")

        # Canonical domain per capability must be computed BEFORE
        # _build_check_to_mappings so the per-mapping `domain` can be overridden.
        self._canonical_domain = self._build_canonical_domains()

        # Build internal lookups
        self._check_to_mappings = self._build_check_to_mappings()
        self._cap_info = self._build_cap_info()
        self._cap_domains = self._build_cap_domains()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: str, label: str) -> list:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"MaturityEngine: {label} file not found at '{path}'"
            )
        if not isinstance(data, list):
            raise ValueError(f"MaturityEngine: {label} must be a JSON array")
        return data

    def _build_canonical_domains(self) -> dict:
        """For each capability_id, pick the canonical domain.

        Priority (highest → lowest):
          1. review_status=approved AND mapping_confidence in {high, medium}
          2. review_status=approved (any confidence)
          3. majority vote across all mappings for this capability
          4. first mapping encountered

        Fixes the bug where auto-generated low-confidence entries with
        `review_status=review_required` leak incorrect domains (e.g.
        `iam_data_perimeters_conditional_access` showing up under
        `resilience` instead of `identity_access`).
        """
        # Collect all (review_status, confidence, domain) tuples per cap
        per_cap: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for m in self._mappings_raw:
            cap_id = m.get("capability_id", "")
            domain = m.get("domain", "")
            if not cap_id or not domain:
                continue
            per_cap[cap_id].append((
                m.get("review_status", ""),
                m.get("mapping_confidence", "low"),
                domain,
            ))

        canonical: dict[str, str] = {}
        for cap_id, entries in per_cap.items():
            # Tier 1: approved + high/medium confidence
            tier1 = [d for s, c, d in entries
                     if s == "approved" and c in ("high", "medium")]
            if tier1:
                canonical[cap_id] = tier1[0]
                continue
            # Tier 2: approved (any confidence)
            tier2 = [d for s, _, d in entries if s == "approved"]
            if tier2:
                canonical[cap_id] = tier2[0]
                continue
            # Tier 3: majority vote
            counts: dict[str, int] = defaultdict(int)
            for _, _, d in entries:
                counts[d] += 1
            canonical[cap_id] = max(counts.items(), key=lambda kv: kv[1])[0]
            # logger.warning(
            #     "MaturityEngine: capability '%s' has no approved mapping — "
            #     "using majority domain '%s' from %d entries.",
            #     cap_id, canonical[cap_id], len(entries),
            # )
        return canonical

    def _build_check_to_mappings(self) -> dict:
        """Build {check_id: [mapping_entry, ...]}.

        Overrides per-mapping `domain` with the capability's canonical domain
        so downstream rollup cannot assign a capability to the wrong domain.
        """
        lookup = defaultdict(list)
        for m in self._mappings_raw:
            check_id = m.get("check_id", "")
            if not check_id:
                continue
            cap_id = m.get("capability_id", "")
            canonical = self._canonical_domain.get(cap_id, m.get("domain", ""))
            lookup[check_id].append({
                "capability_id": cap_id,
                "domain": canonical,
                "mapping_type": m.get("mapping_type", "weak"),
                "mapping_confidence": m.get("mapping_confidence", "low"),
            })
        return dict(lookup)

    def _build_cap_info(self) -> dict:
        """Build {capability_id: capability_object}."""
        info = {}
        for c in self._capabilities_raw:
            cap_id = c.get("capability_id", "")
            if not cap_id:
                continue
            info[cap_id] = {
                "capability_name": c.get("capability_name", ""),
                "stage": c.get("stage", "1 quickwins"),
                "summary": c.get("summary", ""),
                "risk_explanation": c.get("risk_explanation", ""),
                "guidance": c.get("guidance", ""),
                "recommended_practices": c.get("recommended_practices", []),
            }
        return info

    def _build_cap_domains(self) -> dict:
        """Build {capability_id: set(domains)} from canonical domain.

        A capability has exactly one canonical domain (see
        `_build_canonical_domains`), wrapped in a set for compatibility with
        existing downstream code that iterates `set` values.
        """
        domains: dict[str, set] = {}
        for cap_id, canonical in self._canonical_domain.items():
            if canonical:
                domains[cap_id] = {canonical}
        return domains

    # ------------------------------------------------------------------
    # Core scoring: assess()
    # ------------------------------------------------------------------

    def assess(self, findings: list, scanned_services: list = None) -> dict:
        """Score findings and return full maturity assessment.

        Args:
            findings: list of dicts with event_code and status
            scanned_services: optional list of service names (e.g. ["s3", "iam"]).
                If provided, coverage is calculated relative to capabilities
                reachable from those services' checks, not all 78 globally.
        """
        scoped_caps = self._compute_scoped_capabilities(scanned_services)

        if not findings:
            return self._empty_assessment(scoped_caps)

        cap_findings = self._map_findings_to_capabilities(findings)

        if not cap_findings:
            return self._empty_assessment(scoped_caps)

        cap_results = self._score_capabilities(cap_findings)
        domain_results = self._rollup_to_domains(cap_results)
        overall_score, overall_stage = self._compute_overall(domain_results)
        unmapped = self._identify_unmapped(cap_results, scoped_caps)
        confidence = self._confidence_summary(cap_findings)
        coverage = self._compute_coverage(cap_results, scoped_caps, scanned_services)

        return {
            "overall_score": round(overall_score, 1),
            "overall_stage": overall_stage,
            "overall_stage_label": STAGE_LABELS.get(overall_stage, ""),
            "domains": domain_results,
            "unmapped_capabilities": unmapped,
            "confidence_summary": confidence,
            "coverage": coverage,
        }

    # ------------------------------------------------------------------
    # Service-scoped capabilities
    # ------------------------------------------------------------------

    def _compute_scoped_capabilities(self, scanned_services: list = None) -> set | None:
        """Find capabilities reachable from scanned services' checks.

        Returns None if scanned_services is None (global scope).
        Returns set of capability_ids if scoped.
        """
        if not scanned_services:
            return None

        svc_set = {s.lower() for s in scanned_services}
        scoped = set()
        for check_id, mappings in self._check_to_mappings.items():
            prefix = check_id.split("_")[0].lower()
            if prefix in svc_set:
                for m in mappings:
                    scoped.add(m["capability_id"])
        return scoped if scoped else None

    # ------------------------------------------------------------------
    # Step 1: Map findings to capabilities
    # ------------------------------------------------------------------

    def _map_findings_to_capabilities(self, findings: list) -> dict:
        """Map each finding to its capabilities via check_id lookup.

        Returns: {capability_id: [{is_pass, weight, mapping_type, check_id}, ...]}
        """
        cap_findings = defaultdict(list)
        for f in findings:
            check_id = f.get("event_code") or f.get("check_id", "")
            if not check_id:
                continue
            status = f.get("status", "")
            is_pass = 1.0 if status == "PASS" else 0.0

            mappings = self._check_to_mappings.get(check_id, [])
            for m in mappings:
                key = (m["mapping_type"], m["mapping_confidence"])
                weight = _MAPPING_WEIGHTS.get(key, 0.2)
                cap_findings[m["capability_id"]].append({
                    "is_pass": is_pass,
                    "weight": weight,
                    "mapping_type": m["mapping_type"],
                    "mapping_confidence": m["mapping_confidence"],
                    "check_id": check_id,
                    "domain": m["domain"],
                })
        return dict(cap_findings)

    # ------------------------------------------------------------------
    # Step 2: Score capabilities
    # ------------------------------------------------------------------

    def _score_capabilities(self, cap_findings: dict) -> dict:
        """Compute score for each capability.

        Returns: {capability_id: {score, pass_count, fail_count, ...}}
        """
        results = {}
        for cap_id, entries in cap_findings.items():
            total_weight = sum(e["weight"] for e in entries)
            if total_weight == 0:
                score = 0.0
            else:
                score = sum(e["weight"] * e["is_pass"] for e in entries) / total_weight * 100

            pass_count = sum(1 for e in entries if e["is_pass"] == 1.0)
            fail_count = len(entries) - pass_count

            has_direct_or_related = any(
                e["mapping_type"] in ("direct", "related") for e in entries
            )
            status = "assessed" if has_direct_or_related else "partial"

            info = self._cap_info.get(cap_id, {})
            results[cap_id] = {
                "capability_id": cap_id,
                "capability_name": info.get("capability_name", cap_id),
                "stage": info.get("stage", "1 quickwins"),
                "score": round(score, 1),
                "pass_count": pass_count,
                "fail_count": fail_count,
                "total_checks": len(entries),
                "status": status,
                "guidance": info.get("guidance", ""),
                "summary": info.get("summary", ""),
                "risk_explanation": info.get("risk_explanation", ""),
            }
        return results

    # ------------------------------------------------------------------
    # Step 3: Roll up to domains
    # ------------------------------------------------------------------

    def _rollup_to_domains(self, cap_results: dict) -> dict:
        """Group capabilities by domain and compute domain scores."""
        domain_caps = defaultdict(list)
        for cap_id, result in cap_results.items():
            domains = self._cap_domains.get(cap_id, set())
            for domain in domains:
                if domain in DOMAIN_DISPLAY:
                    domain_caps[domain].append(result)

        domain_results = {}
        for domain_id in DOMAIN_DISPLAY:
            caps = domain_caps.get(domain_id, [])
            if not caps:
                domain_results[domain_id] = {
                    "display_name": DOMAIN_DISPLAY[domain_id],
                    "score": 0.0,
                    "stage": "1 quickwins",
                    "stage_label": STAGE_LABELS["1 quickwins"],
                    "capabilities": [],
                    "total_checks": 0,
                    "passed_checks": 0,
                }
                continue

            assessed_caps = [c for c in caps if c["status"] in ("assessed", "partial")]
            if assessed_caps:
                domain_score = sum(c["score"] for c in assessed_caps) / len(assessed_caps)
            else:
                domain_score = 0.0

            stage = self._determine_domain_stage(caps)

            domain_results[domain_id] = {
                "display_name": DOMAIN_DISPLAY[domain_id],
                "score": round(domain_score, 1),
                "stage": stage,
                "stage_label": STAGE_LABELS.get(stage, ""),
                "capabilities": caps,
                "total_checks": sum(c["total_checks"] for c in caps),
                "passed_checks": sum(c["pass_count"] for c in caps),
            }

        return domain_results

    # ------------------------------------------------------------------
    # Step 3b: Stage determination (Task 1.3)
    # ------------------------------------------------------------------

    def _determine_domain_stage(self, caps: list) -> str:
        """Determine domain stage using progressive model.

        A domain achieves a stage only if >= 70% of capabilities at that
        stage score >= 50%, AND all lower stages are also achieved.
        """
        by_stage = defaultdict(list)
        for c in caps:
            by_stage[c["stage"]].append(c)

        achieved = "1 quickwins"

        for stage in STAGE_ORDER:
            stage_caps = by_stage.get(stage, [])
            if not stage_caps:
                continue  # no caps for this stage → skip

            passing = sum(1 for c in stage_caps if c["score"] >= CAPABILITY_PASS_THRESHOLD)
            ratio = passing / len(stage_caps)

            if ratio >= STAGE_COMPLETION_THRESHOLD:
                achieved = stage
            else:
                break  # progressive — can't skip

        return achieved

    # ------------------------------------------------------------------
    # Step 4: Compute overall
    # ------------------------------------------------------------------

    def _compute_overall(self, domain_results: dict) -> tuple:
        """Compute overall score (weighted avg) and stage (weakest link)."""
        domains_with_caps = [
            d for d in domain_results.values() if d["capabilities"]
        ]

        if not domains_with_caps:
            return 0.0, "1 quickwins"

        # Weighted average by number of assessed capabilities
        total_caps = 0
        weighted_sum = 0.0
        for d in domains_with_caps:
            n = len([c for c in d["capabilities"] if c["status"] in ("assessed", "partial")])
            weighted_sum += d["score"] * n
            total_caps += n

        overall_score = weighted_sum / total_caps if total_caps > 0 else 0.0

        # Weakest link for stage
        stages = [d["stage"] for d in domains_with_caps]
        stage_indices = [STAGE_ORDER.index(s) for s in stages if s in STAGE_ORDER]
        overall_stage = STAGE_ORDER[min(stage_indices)] if stage_indices else "1 quickwins"

        return overall_score, overall_stage

    # ------------------------------------------------------------------
    # Step 5: Unmapped capabilities
    # ------------------------------------------------------------------

    def _identify_unmapped(self, cap_results: dict,
                           scoped_caps: set = None) -> list:
        """Find capabilities that have no matching findings.

        If scoped_caps is provided, only list unmapped caps within scope.
        """
        mapped_ids = set(cap_results.keys())
        universe = scoped_caps if scoped_caps else set(self._cap_info.keys())
        unmapped = []
        for cap_id in universe:
            if cap_id not in mapped_ids:
                info = self._cap_info.get(cap_id, {})
                unmapped.append({
                    "capability_id": cap_id,
                    "capability_name": info.get("capability_name", cap_id),
                    "stage": info.get("stage", "1 quickwins"),
                    "guidance": info.get("guidance", ""),
                })
        return unmapped

    # ------------------------------------------------------------------
    # Step 6: Confidence summary
    # ------------------------------------------------------------------

    def _confidence_summary(self, cap_findings: dict) -> dict:
        """Count mappings by confidence level."""
        counts = {"high": 0, "medium": 0, "low": 0}
        for entries in cap_findings.values():
            for e in entries:
                level = e.get("mapping_confidence", "low")
                if level in counts:
                    counts[level] += 1
        return counts

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def _compute_coverage(self, cap_results: dict,
                          scoped_caps: set = None,
                          scanned_services: list = None) -> dict:
        """Compute coverage statistics.

        If scoped_caps is provided, coverage is relative to the scoped set.
        """
        total_global = len(self._cap_info)
        assessed = sum(1 for r in cap_results.values() if r["status"] == "assessed")
        partial = sum(1 for r in cap_results.values() if r["status"] == "partial")

        if scoped_caps:
            scoped_total = len(scoped_caps)
            not_assessed = scoped_total - assessed - partial
            pct = ((assessed + partial) / scoped_total * 100) if scoped_total > 0 else 0.0
        else:
            scoped_total = total_global
            not_assessed = total_global - assessed - partial
            pct = ((assessed + partial) / total_global * 100) if total_global > 0 else 0.0

        return {
            "total_capabilities": total_global,
            "scoped_capabilities": scoped_total,
            "assessed": assessed,
            "partial": partial,
            "not_assessed": not_assessed,
            "mapping_coverage_pct": round(pct, 1),
            "scanned_services": scanned_services or [],
        }

    # ------------------------------------------------------------------
    # Empty assessment
    # ------------------------------------------------------------------

    def _empty_assessment(self, scoped_caps: set = None) -> dict:
        """Return an empty assessment when no findings match."""
        domain_results = {}
        for domain_id, display_name in DOMAIN_DISPLAY.items():
            domain_results[domain_id] = {
                "display_name": display_name,
                "score": 0.0,
                "stage": "1 quickwins",
                "stage_label": STAGE_LABELS["1 quickwins"],
                "capabilities": [],
                "total_checks": 0,
                "passed_checks": 0,
            }

        universe = scoped_caps if scoped_caps else set(self._cap_info.keys())
        unmapped = [
            {
                "capability_id": cap_id,
                "capability_name": self._cap_info.get(cap_id, {}).get("capability_name", cap_id),
                "stage": self._cap_info.get(cap_id, {}).get("stage", "1 quickwins"),
                "guidance": self._cap_info.get(cap_id, {}).get("guidance", ""),
            }
            for cap_id in universe
        ]

        scoped_total = len(scoped_caps) if scoped_caps else len(self._cap_info)

        return {
            "overall_score": 0.0,
            "overall_stage": "1 quickwins",
            "overall_stage_label": STAGE_LABELS["1 quickwins"],
            "domains": domain_results,
            "unmapped_capabilities": unmapped,
            "confidence_summary": {"high": 0, "medium": 0, "low": 0},
            "coverage": {
                "total_capabilities": len(self._cap_info),
                "scoped_capabilities": scoped_total,
                "assessed": 0,
                "partial": 0,
                "not_assessed": scoped_total,
                "mapping_coverage_pct": 0.0,
                "scanned_services": [],
            },
        }

    # ------------------------------------------------------------------
    # compute_delta() — Task 1.4: Pre/Post comparison
    # ------------------------------------------------------------------

    def compute_delta(self, pre: dict, post: dict) -> dict | None:
        """Compare two maturity assessments (pre vs post remediation).

        Returns delta analysis at overall, domain, and capability level.
        Returns None if either input is None.
        """
        if pre is None or post is None:
            return None

        # Overall delta
        overall = {
            "pre_score": pre["overall_score"],
            "post_score": post["overall_score"],
            "score_delta": round(post["overall_score"] - pre["overall_score"], 1),
            "pre_stage": pre["overall_stage"],
            "post_stage": post["overall_stage"],
            "stage_changed": post["overall_stage"] != pre["overall_stage"],
            "stage_label_pre": STAGE_LABELS.get(pre["overall_stage"], ""),
            "stage_label_post": STAGE_LABELS.get(post["overall_stage"], ""),
        }

        # Domain-level delta
        domains = {}
        for domain_id in DOMAIN_DISPLAY:
            pre_domain = pre.get("domains", {}).get(domain_id, {})
            post_domain = post.get("domains", {}).get(domain_id, {})

            pre_score = pre_domain.get("score", 0.0)
            post_score = post_domain.get("score", 0.0)
            pre_stage = pre_domain.get("stage", "1 quickwins")
            post_stage = post_domain.get("stage", "1 quickwins")

            domains[domain_id] = {
                "display_name": DOMAIN_DISPLAY[domain_id],
                "pre_score": pre_score,
                "post_score": post_score,
                "score_delta": round(post_score - pre_score, 1),
                "pre_stage": pre_stage,
                "post_stage": post_stage,
                "stage_changed": post_stage != pre_stage,
            }

        # Capability-level delta
        pre_caps = self._extract_capabilities(pre)
        post_caps = self._extract_capabilities(post)
        all_cap_ids = set(pre_caps.keys()) | set(post_caps.keys())

        improved = []
        unchanged = []
        regressed = []
        stages_unlocked = []

        for cap_id in all_cap_ids:
            pre_cap = pre_caps.get(cap_id)
            post_cap = post_caps.get(cap_id)

            pre_score = pre_cap["score"] if pre_cap else 0.0
            post_score = post_cap["score"] if post_cap else 0.0
            delta = round(post_score - pre_score, 1)

            cap_info = post_cap or pre_cap
            entry = {
                "capability_id": cap_id,
                "capability_name": cap_info.get("capability_name", cap_id),
                "domain": self._get_primary_domain(cap_id),
                "pre_score": pre_score,
                "post_score": post_score,
                "score_delta": delta,
                "newly_passing": pre_score < CAPABILITY_PASS_THRESHOLD and post_score >= CAPABILITY_PASS_THRESHOLD,
            }

            if delta > 0:
                improved.append(entry)
            elif delta < 0:
                regressed.append(entry)
            else:
                unchanged.append(entry)

        # Stage progression detection
        for domain_id in DOMAIN_DISPLAY:
            d = domains[domain_id]
            if d["stage_changed"]:
                pre_idx = STAGE_ORDER.index(d["pre_stage"]) if d["pre_stage"] in STAGE_ORDER else 0
                post_idx = STAGE_ORDER.index(d["post_stage"]) if d["post_stage"] in STAGE_ORDER else 0
                if post_idx > pre_idx:
                    stages_unlocked.append({
                        "domain": domain_id,
                        "display_name": DOMAIN_DISPLAY[domain_id],
                        "from_stage": d["pre_stage"],
                        "to_stage": d["post_stage"],
                    })

        summary = {
            "total_capabilities_affected": len(improved) + len(unchanged) + len(regressed),
            "improved": len(improved),
            "unchanged": len(unchanged),
            "regressed": len(regressed),
            "newly_passing": sum(1 for e in improved if e["newly_passing"]),
            "domains_stage_up": len(stages_unlocked),
        }

        return {
            "overall": overall,
            "domains": domains,
            "capabilities_improved": improved,
            "capabilities_unchanged": unchanged,
            "capabilities_regressed": regressed,
            "stages_unlocked": stages_unlocked,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Helpers for compute_delta
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_capabilities(assessment: dict) -> dict:
        """Flatten all capabilities from domain results into {cap_id: cap_data}."""
        caps = {}
        for domain in assessment.get("domains", {}).values():
            for cap in domain.get("capabilities", []):
                cap_id = cap.get("capability_id", "")
                if cap_id:
                    caps[cap_id] = cap
        return caps

    def _get_primary_domain(self, capability_id: str) -> str:
        """Return the first domain for a capability (for display in delta)."""
        domains = self._cap_domains.get(capability_id, set())
        if domains:
            return next(iter(domains))
        return ""
