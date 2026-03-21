from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.models import (
    Confidence,
    ContextBuildData,
    ContextBundleStats,
    ContextDiagnostics,
    ContextEvidenceItem,
    ContextPayload,
    PromptReadyContext,
    SelectedCapabilityContext,
    SelectedCheckContext,
    SelectedMappingContext,
)


class ContextBuilder:
    """
    Build agent-friendly context packets from a retrieval bundle.

    Expected bundle shape (flexible, best-effort):
    {
        "query": str | None,
        "consumer": "planning" | "risk" | "report",
        "provider": "aws",
        "service": str | None,
        "domain": str | None,
        "check_results": [ ...retrieve result items... ],
        "mapping_results": [ ...mapping items... ],
        "maturity_results": [ ...retrieve result items... ],
        "confidence": "high" | "medium" | "low",
        "review_recommended": bool,
        "warnings": [str, ...],
    }
    """

    def build(
        self,
        bundle: Dict[str, Any],
        consumer: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> ContextBuildData:
        options = options or {}
        max_context_items = int(options.get("max_context_items", 8))
        max_chars_per_item = int(options.get("max_chars_per_item", 600))
        requested_check_ids = {
            str(x).strip().lower()
            for x in self._ensure_list_of_strings(bundle.get("requested_check_ids"))
        }

        query = bundle.get("query")
        confidence = self._normalize_confidence(bundle.get("confidence"))
        review_recommended = bool(bundle.get("review_recommended", False))
        warnings = self._normalize_warnings(bundle.get("warnings", []))

        check_results = self._ensure_list(bundle.get("check_results"))
        mapping_results = self._ensure_list(bundle.get("mapping_results"))
        maturity_results = self._ensure_list(bundle.get("maturity_results"))

        requested_checks, related_checks = self._select_checks(
            check_results=check_results,
            consumer=consumer,
            confidence=confidence,
            review_recommended=review_recommended,
            warnings=warnings,
            max_chars_per_item=max_chars_per_item,
            requested_check_ids=requested_check_ids,
            query=query,
        )

        selected_checks = [*requested_checks, *related_checks]

        # Build a single check signal string for entity gating.
        # This represents the domain of checks actually selected – used by
        # _mapping_passes_entity_gate and _capability_domain_mismatch to
        # prevent product-specific capabilities from appearing when there is
        # no matching product signal in the check IDs or query.
        _check_ids_text = " ".join(c.check_id for c in selected_checks)
        _check_service_text = " ".join(
            c.service for c in selected_checks if c.service
        )
        check_signal = " ".join(filter(None, [
            _check_ids_text,
            _check_service_text,
            bundle.get("service") or "",
            query or "",
        ]))

        selected_mappings = self._select_mappings(
            mapping_results=mapping_results,
            consumer=consumer,
            max_chars_per_item=max_chars_per_item,
            check_signal=check_signal,
        )

        selected_capabilities = self._select_capabilities(
            maturity_results=maturity_results,
            consumer=consumer,
            confidence=confidence,
            review_recommended=review_recommended,
            warnings=warnings,
            max_chars_per_item=max_chars_per_item,
            check_context=check_signal,
        )
        
        risk_bundle = None
        planning_bundle = None
        report_bundle = None

        if consumer == "risk":
            risk_bundle = self._build_risk_bundle(
                requested_checks=requested_checks,
                related_checks=related_checks,
                selected_mappings=selected_mappings,
                selected_capabilities=selected_capabilities,
            )
        elif consumer == "planning":
            planning_bundle = self._build_planning_bundle(
                requested_checks=requested_checks,
                related_checks=related_checks,
                selected_mappings=selected_mappings,
                selected_capabilities=selected_capabilities,
            )
        elif consumer == "report":
            report_bundle = self._build_report_bundle(
                requested_checks=requested_checks,
                related_checks=related_checks,
                selected_mappings=selected_mappings,
                selected_capabilities=selected_capabilities,
            )

        evidence_summary = self._build_evidence_summary(
            selected_checks=selected_checks,
            selected_mappings=selected_mappings,
            selected_capabilities=selected_capabilities,
            max_context_items=max_context_items,
        )

        prompt_ready_context = self._build_prompt_ready_context(
            consumer=consumer,
            query=query,
            requested_checks=requested_checks,
            related_checks=related_checks,
            selected_mappings=selected_mappings,
            selected_capabilities=selected_capabilities,
            confidence=confidence,
            review_recommended=review_recommended,
            warnings=warnings,
        )

        diagnostics = ContextDiagnostics(
            prompt_ready_context=prompt_ready_context,
            bundle_stats=ContextBundleStats(
                check_count=len(selected_checks),
                mapping_count=len(selected_mappings),
                capability_count=len(selected_capabilities),
            ),
            selected_checks=selected_checks,
            selected_mappings=selected_mappings,
            selected_capabilities=selected_capabilities,
            evidence_summary=evidence_summary,
        )

        adjusted_confidence = self._evaluate_bundle_confidence(
             consumer=consumer,
             query=query,
             risk_bundle=risk_bundle,
             report_bundle=report_bundle,
             planning_bundle=planning_bundle,
             retrieval_confidence=confidence,
        )
        if adjusted_confidence:
             diagnostics.adjusted_confidence = adjusted_confidence

        payload = ContextPayload(
            planning_bundle=planning_bundle,
            risk_bundle=risk_bundle,
            report_bundle=report_bundle,
        )

        return ContextBuildData(
            consumer=consumer,
            query=query,
            payload=payload,
            diagnostics=diagnostics,
        )

    def _ensure_list_of_strings(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        result: List[str] = []
        for item in value:
            text = self._maybe_str(item)
            if text:
                result.append(text)
        return result

    # ============================================================
    # Semantic Confidence Evaluation
    # ============================================================

    def _evaluate_bundle_confidence(
        self,
        consumer: str,
        query: Optional[str],
        risk_bundle: Optional[Dict[str, Any]],
        report_bundle: Optional[Dict[str, Any]],
        planning_bundle: Optional[Dict[str, Any]],
        retrieval_confidence: Confidence,
    ) -> Optional[str]:
        """
        Evaluate confidence based on actual payload quality.
        Returns a confidence string ('high', 'medium', 'low') or None if unchanged.
        """
        base_conf = str(retrieval_confidence.value if hasattr(retrieval_confidence, "value") else retrieval_confidence).lower()

        if consumer == "risk" and risk_bundle:
            if not risk_bundle.get("primary_finding"):
                return "low"
            if not risk_bundle.get("control_mapping") and not risk_bundle.get("maturity_context"):
                # We have a finding but no context/mappings
                if base_conf == "high":
                    return "medium"
            return base_conf

        elif consumer == "report" and report_bundle:
            if not report_bundle.get("key_findings") or not report_bundle.get("primary_topics"):
                return "low"
            if not report_bundle.get("control_themes") or not report_bundle.get("recommended_practices"):
                if base_conf == "high":
                    return "medium"
            return base_conf

        elif consumer == "planning" and planning_bundle:
            findings = planning_bundle.get("related_findings") or []
            if not findings:
                return "low"

            intents = self._detect_query_intents(query or "")
            services_covered = {f.get("service") for f in findings if f.get("service")}

            # If multi-intent query but only got 1 service, coverage is poor
            if len(intents) > 1 and len(services_covered) <= 1:
                if base_conf == "high":
                    return "medium"
            return base_conf

        return base_conf

    # ============================================================
    # Selection
    # ============================================================

    def _select_checks(
        self,
        check_results: Sequence[Dict[str, Any]],
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
        max_chars_per_item: int,
        requested_check_ids: Sequence[str],
        query: Optional[str] = None,
    ) -> Tuple[List[SelectedCheckContext], List[SelectedCheckContext]]:
        target_n = self._target_check_count(
            consumer=consumer,
            confidence=confidence,
            review_recommended=review_recommended,
            warnings=warnings,
        )

        requested_ids = {str(x).strip().lower() for x in requested_check_ids}

        requested: List[SelectedCheckContext] = []
        related: List[SelectedCheckContext] = []
        seen_doc_ids: set[str] = set()
        seen_check_ids: set[str] = set()

        # For planning: collect wide candidate pool, then apply coverage-aware selection
        planning_candidates: List[SelectedCheckContext] = []

        for item in check_results:
            doc_id = str(item.get("doc_id") or "").strip()
            metadata = self._ensure_dict(item.get("metadata"))
            check_id = str(metadata.get("check_id") or "").strip()

            if not doc_id or not check_id:
                continue
            if doc_id in seen_doc_ids or check_id in seen_check_ids:
                continue

            short_text = self._compress_check_text(
                item=item, max_chars=max_chars_per_item
            )

            ctx = SelectedCheckContext(
                check_id=check_id,
                doc_id=doc_id,
                service=self._maybe_str(metadata.get("service")),
                title=self._extract_check_title(item),
                short_text=short_text,
                matched_by=self._normalize_str_list(item.get("matched_by")),
                score=self._maybe_float(item.get("score")),
                confidence=confidence,
                metadata=metadata,
            )

            seen_doc_ids.add(doc_id)
            seen_check_ids.add(check_id)

            if consumer == "planning":
                # Collect all candidates up to wide pool limit; diversify after
                planning_candidates.append(ctx)
                if len(planning_candidates) >= target_n:
                    break
            else:
                if check_id.lower() in requested_ids:
                    requested.append(ctx)
                else:
                    related.append(ctx)

                if len(requested) + len(related) >= target_n:
                    break

        if consumer == "planning":
            # Separate exact matches from candidates
            req_candidates = [c for c in planning_candidates if c.check_id.lower() in requested_ids]
            rel_candidates = [c for c in planning_candidates if c.check_id.lower() not in requested_ids]
            # Apply coverage-aware diversification on the full candidate pool
            diversified = self._planning_coverage_select(
                candidates=planning_candidates,
                query=query,
            )
            for c in diversified:
                if c.check_id.lower() in requested_ids:
                    requested.append(c)
                else:
                    related.append(c)
            return requested, related

        return requested, related

    # ============================================================
    # Planning: intent detection + coverage-aware diversification
    # ============================================================

    # Semantic intent clusters: each cluster is a set of keywords
    # If a query contains any keyword from a cluster, that intent is "active"
    _INTENT_CLUSTERS: Dict[str, List[str]] = {
        "encryption": ["encrypt", "kms", "ssl", "tls", "at rest", "in transit", "cmk"],
        "public_access": ["public", "exposed", "open", "unrestricted", "internet"],
        "iam": ["iam", "user", "role", "permission", "policy", "password", "mfa", "credential"],
        "logging": ["log", "cloudtrail", "audit", "trail", "monitoring", "cloudwatch"],
        "network": ["vpc", "sg", "security group", "nacl", "network", "port", "ingress", "egress", "firewall"],
        "backup": ["backup", "snapshot", "recovery", "retention", "rto", "rpo"],
        "access_control": ["access", "control", "restrict", "allow", "deny", "block"],
        "root": ["root", "admin", "superuser"],
        "secrets": ["secret", "key", "token", "api key", "credential", "password"],
    }

    def _detect_query_intents(self, query: Optional[str]) -> List[str]:
        """
        Identify distinct semantic intents present in the query via keyword cluster matching.
        Returns a list of active intent names (e.g. ["encryption", "public_access"]).
        """
        if not query:
            return []
        q = query.lower()
        active: List[str] = []
        for intent_name, keywords in self._INTENT_CLUSTERS.items():
            if any(kw in q for kw in keywords):
                active.append(intent_name)
        return active

    def _planning_coverage_select(
        self,
        candidates: Sequence[SelectedCheckContext],
        query: Optional[str],
    ) -> List[SelectedCheckContext]:
        """
        Greedy coverage selection for planning consumer.

        Strategy:
        1. Detect active intents from the query.
        2. Dynamic target = clamp(len(intents) * 2, min=2, max=8).
           - narrow query (0-1 intents) → 2-3 checks
           - medium query (2-3 intents) → 4-6 checks
           - wide query (4+ intents)  → 6-8 checks
        3. First pass: pick one check per (intent, service) pair that best
           represents that intent, choosing highest-scored candidate that
           matches keyword cluster.
        4. Second pass: fill remaining slots with high-score candidates
           that add new service coverage.
        5. Final pass: fill remaining slots with highest remaining scores.
        """
        if not candidates:
            return []

        intents = self._detect_query_intents(query)
        n_intents = len(intents)
        # Dynamic target: 2 checks per intent, clamp [2, 8]
        dynamic_target = max(2, min(8, n_intents * 2 if n_intents > 0 else 3))

        selected: List[SelectedCheckContext] = []
        selected_ids: set[str] = set()
        covered_intents: set[str] = set()
        covered_services: set[str] = set()

        # Helper: score of a candidate (fallback to 0)
        def score_of(c: SelectedCheckContext) -> float:
            return c.score or 0.0

        def intent_priority(c: SelectedCheckContext) -> float:
            check_id = (c.check_id or "").lower()
            text = " ".join(
                filter(
                    None,
                    [
                        c.check_id,
                        c.title,
                        c.short_text,
                        self._ensure_dict(c.metadata).get("description", ""),
                    ],
                )
            ).lower()
            boost = 0.0
            if "public_access" in intents:
                if "public_access" in check_id or "public_access_block" in check_id:
                    boost += 0.40
                if "public" in text and ("acl" in text or "policy" in text):
                    boost += 0.15
            if "encryption" in intents:
                if "secure_transport" in check_id or "https" in check_id:
                    boost += 0.25
                if "default_encryption" in check_id or "kms_encryption" in check_id:
                    boost += 0.25
            if "logging" in intents and ("cloudtrail" in text or "log" in text):
                boost += 0.10
            return boost

        def check_matches_intent(c: SelectedCheckContext, intent: str) -> bool:
            keywords = self._INTENT_CLUSTERS.get(intent, [])
            text = " ".join(filter(None, [
                c.check_id, c.title, c.short_text,
                self._ensure_dict(c.metadata).get("description", ""),
            ])).lower()
            return any(kw in text for kw in keywords)

        # --- Pass 1: one representative per intent ---
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (intent_priority(c), score_of(c)),
            reverse=True,
        )
        for intent in intents:
            if intent in covered_intents:
                continue
            best: Optional[SelectedCheckContext] = None
            for c in sorted_candidates:
                if c.check_id in selected_ids:
                    continue
                if check_matches_intent(c, intent):
                    best = c
                    break
            if best:
                selected.append(best)
                selected_ids.add(best.check_id)
                covered_intents.add(intent)
                if best.service:
                    covered_services.add(best.service.lower())

        # --- Pass 2: new service coverage ---
        for c in sorted_candidates:
            if len(selected) >= dynamic_target:
                break
            if c.check_id in selected_ids:
                continue
            svc = (c.service or "").lower()
            if svc and svc not in covered_services:
                selected.append(c)
                selected_ids.add(c.check_id)
                if svc:
                    covered_services.add(svc)

        # --- Pass 3: fill by score ---
        for c in sorted_candidates:
            if len(selected) >= dynamic_target:
                break
            if c.check_id in selected_ids:
                continue
            selected.append(c)
            selected_ids.add(c.check_id)

        return selected

    def _select_mappings(
        self,
        mapping_results: Sequence[Dict[str, Any]],
        consumer: str,
        max_chars_per_item: int,
        check_signal: Optional[str] = None,
    ) -> List[SelectedMappingContext]:
        target_n = 2 if consumer == "planning" else 3

        selected: List[SelectedMappingContext] = []
        seen_pairs: set[Tuple[str, str]] = set()

        sorted_items = sorted(mapping_results, key=self._mapping_sort_key)

        for item in sorted_items:
            check_id = self._maybe_str(item.get("check_id")) or self._maybe_str(
                item.get("source_check_id")
            )
            capability_id = self._maybe_str(item.get("capability_id"))
            if not check_id or not capability_id:
                continue

            pair = (check_id, capability_id)
            if pair in seen_pairs:
                continue

            # --- Entity Gating: reject mappings that are semantic mismatches ---
            if not self._mapping_passes_entity_gate(
                check_id=check_id,
                capability_id=capability_id,
                capability_name=self._maybe_str(item.get("capability_name")),
                mapping_confidence=item.get("mapping_confidence"),
                mapping_type=item.get("mapping_type"),
                review_status=item.get("review_status"),
                check_signal=check_signal or check_id,
            ):
                continue

            rationale = self._compress_text(
                item.get("mapping_reason") or item.get("rationale") or "",
                max_chars=max_chars_per_item,
            )

            selected.append(
                SelectedMappingContext(
                    check_id=check_id,
                    capability_id=capability_id,
                    capability_name=self._maybe_str(item.get("capability_name")),
                    mapping_confidence=self._normalize_confidence(
                        item.get("mapping_confidence")
                    ),
                    mapping_type=self._maybe_str(item.get("mapping_type")),
                    review_status=self._maybe_str(item.get("review_status")),
                    rationale=rationale or None,
                    metadata=self._ensure_dict(item),
                )
            )
            seen_pairs.add(pair)

            if len(selected) >= target_n:
                break

        return selected

    # ============================================================
    # Mapping governance: entity gates
    # ============================================================

    # Map: product entity tokens → required matching signals in the check
    # A capability whose name/id contains any key token MUST match at least
    # one signal token from the associated list in the check_id/check signal.
    _PRODUCT_ENTITY_GATES: Dict[str, List[str]] = {
        "bedrock":    ["bedrock", "genai", "gen_ai", "generative", "llm", "foundationmodel", "foundation_model", "fm", "prompt"],
        "genai":      ["bedrock", "genai", "gen_ai", "generative", "llm", "ai", "ml", "prompt"],
        "generative": ["bedrock", "genai", "gen_ai", "generative", "llm", "ai", "prompt"],
        "prompt":     ["bedrock", "genai", "llm", "prompt", "inference"],
        "sagemaker":  ["sagemaker", "sagemaker_", "_sagemaker", "training", "endpoint", "ml", "model"],
        "guardduty":  ["guardduty", "guard_duty", "threat", "malware"],
        "macie":      ["macie", "sensitive", "pii", "data_classification"],
        "inspector":  ["inspector", "vulnerability", "cve", "ecr"],
        "waf":        ["waf", "web_acl", "webacl", "rate_limit", "sql_injection", "xss"],
        "shield":     ["shield", "ddos", "dos"],
        "securityhub":["securityhub", "security_hub", "hub"],
    }

    _CONTROL_FAMILY_GATES: Dict[str, List[str]] = {
        "public_access": [
            "public access",
            "publicly accessible",
            "public exposure",
            "public read",
            "public write",
            "anonymous access",
            "unauthenticated access",
            "internet exposed",
            "block public access",
        ],
        "encryption_at_rest": [
            "encryption at rest",
            "default encryption",
            "server side encryption",
            "kms",
            "sse",
            "stored data",
            "storage encryption",
        ],
        "encryption_in_transit": [
            "encryption in transit",
            "secure transport",
            "https",
            "tls",
            "ssl",
            "secure protocol",
        ],
        "logging_monitoring": [
            "logging",
            "cloudtrail",
            "audit",
            "monitoring",
            "detection",
        ],
        "identity_access": [
            "identity",
            "iam",
            "least privilege",
            "mfa",
            "password",
            "credential",
            "role",
            "permission",
        ],
    }

    def _infer_control_families(self, text: str) -> set[str]:
        normalized = (text or "").lower()
        families: set[str] = set()
        for family, markers in self._CONTROL_FAMILY_GATES.items():
            if any(marker in normalized for marker in markers):
                families.add(family)
        return families

    def _mapping_passes_entity_gate(
        self,
        check_id: str,
        capability_id: str,
        capability_name: Optional[str],
        mapping_confidence: Any,
        mapping_type: Any,
        review_status: Any,
        check_signal: str,
    ) -> bool:
        """
        Returns False if the capability contains a product-specific entity
        that requires matching signals in the check, but no such signals exist.

        Rule steps:
        1. Build a combined capability text (id + name).
        2. For each product entity token in _PRODUCT_ENTITY_GATES:
           - If capability_text contains the token:
             a. Check whether check_signal contains at least one required signal.
             b. If NOT: reject the mapping (entity gate blocks).
        3. Additionally, if confidence is low AND type is weak AND
           review_status is draft/review_required, reject this mapping
           even if no product entity was found (prevents noise in payload).
        """
        cap_text = " ".join(filter(None, [capability_id, capability_name or ""])).lower()
        check_text = check_signal.lower()

        for entity_token, required_signals in self._PRODUCT_ENTITY_GATES.items():
            if entity_token in cap_text:
                # Capability is product-specific; require at least one signal match
                if not any(sig in check_text for sig in required_signals):
                    return False  # entity gate blocked: semantic mismatch

        capability_families = self._infer_control_families(cap_text)
        check_families = self._infer_control_families(check_text)
        if capability_families and check_families and not (
            capability_families & check_families
        ):
            return False

        # Low-quality mapping gate: weak + low confidence + not reviewed
        conf = (self._maybe_str(mapping_confidence) or "").lower()
        mtype = (self._maybe_str(mapping_type) or "").lower()
        rstatus = (self._maybe_str(review_status) or "").lower()

        is_weak_quality = (
            conf == "low"
            and mtype in {"weak", "indirect", "fuzzy", "tentative", "unconfirmed"}
            and rstatus in {"draft", "review_required", "pending"}
        )
        if is_weak_quality:
            return False

        return True

    def _capability_domain_mismatch(
        self,
        capability_id: str,
        capability_name: Optional[str],
        check_context: str,
    ) -> bool:
        """
        Returns True if the capability has a product-specific entity
        that is NOT supported by the check context.
        Used to filter `_select_capabilities` results.
        """
        cap_text = " ".join(filter(None, [capability_id, capability_name or ""])).lower()
        check_text = check_context.lower()

        for entity_token, required_signals in self._PRODUCT_ENTITY_GATES.items():
            if entity_token in cap_text:
                if not any(sig in check_text for sig in required_signals):
                    return True  # mismatch detected

        capability_families = self._infer_control_families(cap_text)
        check_families = self._infer_control_families(check_text)
        if capability_families and check_families and not (
            capability_families & check_families
        ):
            return True

        return False

    def _select_capabilities(
        self,
        maturity_results: Sequence[Dict[str, Any]],
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
        max_chars_per_item: int,
        check_context: Optional[str] = None,
    ) -> List[SelectedCapabilityContext]:
        target_n = self._target_capability_count(
            consumer=consumer,
            confidence=confidence,
            review_recommended=review_recommended,
            warnings=warnings,
        )

        selected: List[SelectedCapabilityContext] = []
        seen_doc_ids: set[str] = set()
        seen_capability_ids: set[str] = set()

        for item in maturity_results:
            doc_id = str(item.get("doc_id") or "").strip()
            metadata = self._ensure_dict(item.get("metadata"))
            capability_id = str(metadata.get("capability_id") or "").strip()

            if not doc_id or not capability_id:
                continue
            if doc_id in seen_doc_ids or capability_id in seen_capability_ids:
                continue

            cap_name = self._extract_capability_name(item)

            # --- Domain mismatch gate: skip product-specific capabilities ---
            # that have no signal match in the check context
            if check_context and self._capability_domain_mismatch(
                capability_id=capability_id,
                capability_name=cap_name,
                check_context=check_context,
            ):
                continue

            short_text = self._compress_capability_text(
                item=item, max_chars=max_chars_per_item
            )

            selected.append(
                SelectedCapabilityContext(
                    capability_id=capability_id,
                    doc_id=doc_id,
                    capability_name=cap_name,
                    domain=self._maybe_str(metadata.get("domain")),
                    short_text=short_text,
                    score=self._maybe_float(item.get("score")),
                    confidence=confidence,
                    metadata=metadata,
                )
            )
            seen_doc_ids.add(doc_id)
            seen_capability_ids.add(capability_id)

            if len(selected) >= target_n:
                break

        return selected

    # ============================================================
    # Evidence summary
    # ============================================================

    def _build_evidence_summary(
        self,
        selected_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
        max_context_items: int,
    ) -> List[ContextEvidenceItem]:
        items: List[ContextEvidenceItem] = []

        for check in selected_checks:
            items.append(
                ContextEvidenceItem(
                    doc_id=check.doc_id,
                    source_type=str(
                        check.metadata.get("source_type", "retrieval_result")
                    ),
                    doc_type="prowler_check",
                    title=check.title or check.check_id,
                    short_text=check.short_text,
                    why_selected="Selected as a primary technical control/check match.",
                    score=check.score,
                    confidence=check.confidence,
                    metadata=check.metadata,
                )
            )

        for mapping in selected_mappings:
            items.append(
                ContextEvidenceItem(
                    doc_id=f"mapping:{mapping.check_id}:{mapping.capability_id}",
                    source_type="mapping",
                    doc_type="maturity_mapping",
                    title=f"{mapping.check_id} -> {mapping.capability_id}",
                    short_text=mapping.rationale
                    or "Mapping links the check to a maturity capability.",
                    why_selected="Selected to connect technical findings with maturity guidance.",
                    score=None,
                    confidence=mapping.mapping_confidence,
                    metadata=mapping.metadata,
                )
            )

        for capability in selected_capabilities:
            items.append(
                ContextEvidenceItem(
                    doc_id=capability.doc_id,
                    source_type=str(
                        capability.metadata.get("source_type", "retrieval_result")
                    ),
                    doc_type="maturity_capability",
                    title=capability.capability_name or capability.capability_id,
                    short_text=capability.short_text,
                    why_selected="Selected as supporting control and best-practice context.",
                    score=capability.score,
                    confidence=capability.confidence,
                    metadata=capability.metadata,
                )
            )

        return items[:max_context_items]

    # ============================================================
    # Prompt-ready formatting
    # ============================================================

    def _build_prompt_ready_context(
        self,
        consumer: str,
        query: Optional[str],
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> PromptReadyContext:
        header_lines = [
            f"Context consumer: {consumer}",
            f"Primary query: {query or '(not provided)'}",
            f"Overall retrieval confidence: {confidence.value}",
            f"Review recommended: {'true' if review_recommended else 'false'}",
        ]
        if warnings:
            header_lines.append(f"Warnings: {', '.join(warnings)}")

        evidence_sections: List[str] = []

        if requested_checks:
            check_lines = ["[Requested Checks]"]
            for item in requested_checks:
                line = f"- {item.check_id}"
                if item.service:
                    line += f" (service: {item.service})"
                if item.short_text:
                    line += f": {item.short_text}"
                check_lines.append(line)
            evidence_sections.append("\n".join(check_lines))

        if related_checks:
            related_lines = ["[Related Checks]"]
            for item in related_checks:
                line = f"- {item.check_id}"
                if item.service:
                    line += f" (service: {item.service})"
                if item.short_text:
                    line += f": {item.short_text}"
                related_lines.append(line)
            evidence_sections.append("\n".join(related_lines))

        if selected_mappings:
            mapping_lines = ["[Selected Mappings]"]
            for item in selected_mappings:
                line = f"- {item.check_id} -> {item.capability_id}"
                if item.mapping_confidence:
                    line += f" (mapping_confidence: {item.mapping_confidence.value})"
                if item.rationale:
                    line += f": {item.rationale}"
                mapping_lines.append(line)
            evidence_sections.append("\n".join(mapping_lines))

        if selected_capabilities:
            capability_lines = ["[Selected Capabilities]"]
            for item in selected_capabilities:
                label = item.capability_name or item.capability_id
                line = f"- {label}"
                if item.short_text:
                    line += f": {item.short_text}"
                capability_lines.append(line)
            evidence_sections.append("\n".join(capability_lines))

        guidance_block = self._build_guidance_block(
            consumer=consumer,
            confidence=confidence,
            review_recommended=review_recommended,
            warnings=warnings,
        )

        return PromptReadyContext(
            header="\n".join(header_lines),
            evidence_block="\n\n".join(evidence_sections).strip(),
            guidance_block=guidance_block,
        )

    def _build_guidance_block(
        self,
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> str:
        base_lines: List[str] = []

        if consumer == "planning":
            base_lines.append(
                "Use the selected checks to decide which checks or services should be scanned next."
            )
            base_lines.append(
                "Prefer exact or top-ranked check matches as anchors for planning."
            )
        elif consumer == "risk":
            base_lines.append(
                "Use the selected checks as primary technical evidence for the finding."
            )
            base_lines.append(
                "Use mappings and capabilities as supporting control context for risk analysis."
            )
        else:
            base_lines.append(
                "Use the selected checks as factual technical evidence in the report."
            )
            base_lines.append(
                "Use mappings and capabilities to explain control intent, best practices, and remediation direction."
            )

        if confidence == Confidence.low or review_recommended:
            base_lines.append(
                "Do not make overly certain claims. Phrase conclusions carefully and acknowledge uncertainty where needed."
            )

        if warnings:
            base_lines.append(
                f"Pay attention to these warnings: {', '.join(warnings)}."
            )

        return "\n".join(base_lines)

    # ============================================================
    # Compression helpers
    # ============================================================

    def _compress_check_text(self, item: Dict[str, Any], max_chars: int) -> str:
        metadata = self._ensure_dict(item.get("metadata"))
        title = self._extract_check_title(item)
        check_id = self._maybe_str(metadata.get("check_id"))

        description = self._first_non_empty(
            metadata.get("description"),
            metadata.get("risk"),
            metadata.get("remediation"),
            metadata.get("retrieval_text"),
        )

        title_norm = self._normalize_whitespace(title or "").lower()
        desc_norm = self._normalize_whitespace(description or "").lower()

        parts = []
        if title:
            parts.append(title)

        if description and desc_norm != title_norm:
            parts.append(description)

        if not parts and check_id:
            parts.append(check_id)

        return self._compress_text(". ".join(parts), max_chars=max_chars)

    def _compress_capability_text(self, item: Dict[str, Any], max_chars: int) -> str:
        metadata = self._ensure_dict(item.get("metadata"))
        capability_name = self._extract_capability_name(item)

        summary = self._first_non_empty(
            metadata.get("summary"),
            metadata.get("risk_explanation"),
            metadata.get("guidance"),
            metadata.get("retrieval_text"),
        )

        parts = []
        if capability_name:
            parts.append(capability_name)
        if summary:
            parts.append(summary)

        return self._compress_text(". ".join(parts), max_chars=max_chars)

    def _compress_text(self, value: Any, max_chars: int) -> str:
        text = self._normalize_whitespace(str(value or ""))
        if len(text) <= max_chars:
            return text
        if max_chars <= 3:
            return text[:max_chars]
        return text[: max_chars - 3].rstrip() + "..."

    # ============================================================
    # Threshold / count helpers
    # ============================================================

    def _target_check_count(
        self,
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> int:
        if consumer == "planning":
            # Wide candidate pool for planning – coverage selection trims this down
            return 15
        if consumer == "risk":
            return 3
        return 3

    def _target_capability_count(
        self,
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> int:
        if consumer == "planning":
            return 1
        if consumer == "risk":
            return (
                3
                if self._should_expand(confidence, review_recommended, warnings)
                else 2
            )
        return 3

    def _should_expand(
        self,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> bool:
        if review_recommended:
            return True
        if confidence == Confidence.low:
            return True
        lowered = {w.lower() for w in warnings}
        return "ambiguous_top_results" in lowered or "low_score_top1" in lowered

    # ============================================================
    # Utility helpers
    # ============================================================

    def _mapping_sort_key(self, item: Dict[str, Any]) -> Tuple[int, int, float]:
        review_status = (self._maybe_str(item.get("review_status")) or "").lower()
        mapping_type = (self._maybe_str(item.get("mapping_type")) or "").lower()
        confidence = self._normalize_confidence(item.get("mapping_confidence"))
        score = self._maybe_float(item.get("score")) or 0.0

        review_rank = 0 if review_status in {"approved", "reviewed", "accepted"} else 1
        type_rank = 0 if mapping_type in {"curated", "manual", "strong"} else 1
        conf_rank = {
            Confidence.high: 0,
            Confidence.medium: 1,
            Confidence.low: 2,
        }[confidence]

        return (review_rank, type_rank + conf_rank, -score)

    def _extract_check_title(self, item: Dict[str, Any]) -> Optional[str]:
        metadata = self._ensure_dict(item.get("metadata"))
        return self._first_non_empty(
            metadata.get("title"),
            metadata.get("name"),
            item.get("title"),
        )

    def _extract_capability_name(self, item: Dict[str, Any]) -> Optional[str]:
        metadata = self._ensure_dict(item.get("metadata"))
        return self._first_non_empty(
            metadata.get("capability_name"),
            metadata.get("title"),
            metadata.get("name"),
            item.get("capability_name"),
            item.get("title"),
            metadata.get("capability_id"),
            item.get("capability_id"),
        )

    def _normalize_confidence(self, value: Any) -> Confidence:
        if isinstance(value, Confidence):
            return value
        text = str(value or "").strip().lower()
        if text == "high":
            return Confidence.high
        if text == "medium":
            return Confidence.medium
        return Confidence.low

    def _normalize_warnings(self, warnings: Any) -> List[str]:
        result: List[str] = []
        if isinstance(warnings, list):
            for item in warnings:
                text = self._maybe_str(item)
                if text:
                    result.append(text)
        elif warnings:
            text = self._maybe_str(warnings)
            if text:
                result.append(text)
        return result

    def _normalize_str_list(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        result: List[str] = []
        for item in value:
            text = self._maybe_str(item)
            if text:
                result.append(text)
        return result

    def _ensure_list(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        result: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                result.append(item)
        return result

    def _ensure_dict(self, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _maybe_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _maybe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _first_non_empty(self, *values: Any) -> Optional[str]:
        for value in values:
            text = self._maybe_str(value)
            if text:
                return text
        return None

    def _normalize_whitespace(self, text: str) -> str:
        return " ".join(text.split())


    @staticmethod
    def _truncate_text(text: Optional[str], max_length: int = 200) -> Optional[str]:
        if not text:
            return None
        return text[:max_length] + "..." if len(text) > max_length else text

    def _normalize_check_item(
        self,
        item: "SelectedCheckContext",
        include_remediation: bool = True,
    ) -> Dict[str, Any]:
        """
        Shared, authoritative transform from SelectedCheckContext -> bundle-ready dict.
        Reads description/risk/remediation from item.metadata (original source document).
        Falls back to None only when the source field truly does not exist.
        """
        meta = self._ensure_dict(item.metadata)
        return {
            "check_id": item.check_id,
            "service": item.service,
            "title": item.title,
            "severity": meta.get("severity"),
            "description": meta.get("description") or None,
            "risk": meta.get("risk") or None,
            "remediation": meta.get("remediation") or None if include_remediation else None,
        }

    def _build_risk_bundle(
        self,
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
    ) -> Dict[str, Any]:
        """
        Risk bundle provides broader context, mappings, and related findings
        to help evaluate the impact of a violation.
        Technical fields (description, risk, remediation) are sourced from
        the original check metadata and are never replaced with a fallback.
        """
        primary_finding: Optional[Dict[str, Any]] = None
        
        if requested_checks:
            primary_finding = self._normalize_check_item(requested_checks[0], include_remediation=True)

        related_findings: List[Dict[str, Any]] = [
            {
                "check_id": item.check_id,
                "service": item.service,
                "title": item.title,
                "severity": self._ensure_dict(item.metadata).get("severity"),
            }
            for item in related_checks
        ]

        control_mapping: List[Dict[str, Any]] = []
        for item in selected_mappings:
            confidence_val = item.mapping_confidence.value if hasattr(item.mapping_confidence, "value") else item.mapping_confidence
            control_mapping.append(
                {
                    "check_id": item.check_id,
                    "capability_id": item.capability_id,
                    "mapping_confidence": confidence_val,
                }
            )

        maturity_context: List[Dict[str, Any]] = []
        for item in selected_capabilities:
            maturity_context.append(
                {
                    "capability_id": item.capability_id,
                    "capability_name": item.capability_name,
                    "short_text": item.short_text,
                }
            )

        return {
            "primary_finding": primary_finding,
            "related_findings": related_findings,
            "control_mapping": control_mapping,
            "maturity_context": maturity_context,
        }

    def _build_planning_bundle(
        self,
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
    ) -> Dict[str, Any]:
        """
        Planning bundle emphasizes check metadata (ID, service, severity)
        useful for determining scope and relevance.
        """
        related_findings: List[Dict[str, Any]] = []
        
        all_checks = list(requested_checks) + list(related_checks)
        seen_checks = set()
        
        for item in all_checks:
            if item.check_id in seen_checks:
                continue
            seen_checks.add(item.check_id)
            meta = self._ensure_dict(item.metadata)
            related_findings.append(
                {
                    "check_id": item.check_id,
                    "service": item.service,
                    "title": item.title,
                    "severity": meta.get("severity"),
                }
            )

        control_mapping_ids = [item.capability_id for item in selected_mappings if item.capability_id]
        maturity_capability_ids = [item.capability_id for item in selected_capabilities if item.capability_id]

        return {
            "related_findings": related_findings,
            "control_mapping_ids": control_mapping_ids,
            "maturity_capability_ids": maturity_capability_ids,
        }

    def _build_report_bundle(
        self,
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
    ) -> Dict[str, Any]:
        """
        Report bundle synthesizes aggregated themes, key findings, and 
        consolidated recommended practices for narrative generation.
        """
        all_checks = list(requested_checks) + list(related_checks)
        seen_checks = set()
        key_findings = []
        primary_topics_set = set()
        
        for item in all_checks:
            if item.check_id in seen_checks:
                continue
            seen_checks.add(item.check_id)
            
            if item.service:
                primary_topics_set.add(item.service.lower())
                
            meta = self._ensure_dict(item.metadata)
            risk_summary = self._truncate_text(meta.get("risk") or meta.get("description"))
            
            key_findings.append({
                "check_id": item.check_id,
                "title": item.title,
                "severity": meta.get("severity"),
                "risk_summary": risk_summary
            })
            
        primary_topics = sorted(list(primary_topics_set))

        control_themes = []
        practices_set = set()
        
        # First, try to extract practices from selected capabilities
        for item in selected_capabilities:
            meta = self._ensure_dict(item.metadata)
            control_themes.append({
                "capability_id": item.capability_id,
                "capability_name": item.capability_name,
                "summary_short": self._truncate_text(meta.get("summary")) or "",
            })
            
            raw_practices = meta.get("recommended_practices") or []
            for p in raw_practices:
                practices_set.add(p)

        # If no capability context, fall back to mappings as lightweight themes.
        if not control_themes and selected_mappings:
            for mapping in selected_mappings:
                control_themes.append({
                    "capability_id": mapping.capability_id,
                    "capability_name": mapping.capability_name,
                    "summary_short": self._truncate_text(mapping.rationale) or "",
                })

        # If still no practices, use mapping rationale as a minimal practice hint.
        if not practices_set and selected_mappings:
            for mapping in selected_mappings:
                if mapping.rationale:
                    practices_set.add(mapping.rationale)
                
        # If no practices were found from capabilities, or if capabilities are empty,
        # fall back to extracting practices from check metadata
        if not practices_set and all_checks:
            for item in all_checks:
                meta = self._ensure_dict(item.metadata)
                raw_practices = meta.get("recommended_practices") or []
                for p in raw_practices:
                    practices_set.add(p)

        # As a last resort, use remediation text from checks to avoid empty bundles.
        if not practices_set and all_checks:
            for item in all_checks:
                meta = self._ensure_dict(item.metadata)
                remediation = meta.get("remediation")
                if remediation:
                    practices_set.add(remediation)

        # Clean and top 5 unique practices
        recommended_practices = [self._truncate_text(p, 150) for p in sorted(list(practices_set))][:5]

        return {
            "primary_topics": primary_topics,
            "key_findings": key_findings,
            "control_themes": control_themes,
            "recommended_practices": recommended_practices,
        }
