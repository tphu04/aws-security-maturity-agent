"""Merge an external LLM's review of `golden_set_additions_draft.json` into
the final `golden_set.json`.

Workflow:
  1. User pastes `golden_set_review_packet.md` into ChatGPT/Claude.ai.
  2. External LLM returns a JSON array of verdicts (one per draft entry).
  3. User saves that response to `external_review_response.json` (raw text
     is fine — the parser strips markdown fences).
  4. Run this script.

The script:
  - Parses the response (tolerant: handles ```json fences, prose around
    JSON, mixed objects-vs-arrays).
  - Applies verdicts:
      * verdict=agree     -> keep proposed mapping, mark verified=True
      * verdict=partial   -> keep proposed, mark verified=partial, save comment
      * verdict=disagree  -> if `better_capability_id` is in catalog,
                             use that; else move to `rejected` bucket.
  - Validates resulting check_id/capability_id against actual catalogs.
  - Appends accepted entries to `golden_set.json` (no duplicates by check_id).
  - Writes audit log of decisions to `external_review_audit.json`.

Run:
    python -m RAG.pipeline.mapping.tier4_validation.merge_external_review \\
        --response external_review_response.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> List[Dict[str, Any]]:
    """Pull the first JSON array out of the response, tolerant to prose."""
    candidates: List[str] = []

    # Markdown fences first — they're the most reliable signal.
    for m in _FENCE_RE.finditer(raw):
        candidates.append(m.group(1).strip())

    # Fall back to "first '[' to matching ']'" scan.
    if not candidates:
        start = raw.find("[")
        if start >= 0:
            depth = 0
            for i in range(start, len(raw)):
                if raw[i] == "[":
                    depth += 1
                elif raw[i] == "]":
                    depth -= 1
                    if depth == 0:
                        candidates.append(raw[start : i + 1])
                        break

    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and isinstance(parsed.get("verdicts"), list):
                return parsed["verdicts"]
        except Exception:
            continue

    raise ValueError(
        "Could not extract a JSON array of verdicts from the response. "
        "Expected shape: [{\"id\": 1, \"verdict\": \"agree|partial|disagree\", "
        "\"better_capability_id\": \"...|null\", \"comment\": \"...\"}, ...]"
    )


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _save_json(p: Path, data: Any) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge(
    response_path: Path,
    draft_path: Path,
    golden_path: Path,
    capabilities_path: Path,
    prowler_path: Path,
    audit_path: Path,
) -> Dict[str, Any]:
    raw = response_path.read_text(encoding="utf-8")
    verdicts = _extract_json(raw)

    draft = _load_json(draft_path)
    golden = _load_json(golden_path)
    capability_ids = {
        c["capability_id"]
        for c in _load_json(capabilities_path) if c.get("capability_id")
    }
    check_ids = {
        c["CheckID"] for c in _load_json(prowler_path) if c.get("CheckID")
    }

    draft_by_index = {i + 1: m for i, m in enumerate(draft["mappings"])}
    existing_check_ids = {m["check_id"] for m in golden["mappings"]}

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []

    for v in verdicts:
        idx = v.get("id")
        verdict = (v.get("verdict") or "").strip().lower()
        better = v.get("better_capability_id")
        if isinstance(better, str) and better.strip().lower() in {"null", "none", ""}:
            better = None
        comment = (v.get("comment") or "").strip()

        if idx not in draft_by_index:
            audit.append({"id": idx, "outcome": "skipped_unknown_id", "comment": comment})
            continue

        entry = dict(draft_by_index[idx])

        if entry["check_id"] not in check_ids:
            audit.append({"id": idx, "check_id": entry["check_id"],
                          "outcome": "skipped_check_not_in_prowler"})
            continue

        if entry["check_id"] in existing_check_ids:
            audit.append({"id": idx, "check_id": entry["check_id"],
                          "outcome": "skipped_already_in_golden"})
            continue

        if verdict == "agree":
            entry["verification"] = {
                "verified": True,
                "verified_by": "external_llm_review",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "reviewer_comment": comment,
            }
            accepted.append(entry)
            audit.append({"id": idx, "check_id": entry["check_id"],
                          "outcome": "accepted_agree"})
        elif verdict == "partial":
            entry["verification"] = {
                "verified": "partial",
                "verified_by": "external_llm_review",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "reviewer_comment": comment,
            }
            accepted.append(entry)
            audit.append({"id": idx, "check_id": entry["check_id"],
                          "outcome": "accepted_partial"})
        elif verdict == "disagree":
            if better and better in capability_ids:
                entry["expected_capability_id"] = better
                entry["verification"] = {
                    "verified": True,
                    "verified_by": "external_llm_review",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "reviewer_comment": (
                        f"Original draft suggested different capability. "
                        f"External reviewer corrected: {comment}"
                    ),
                    "corrected_from": draft_by_index[idx]["expected_capability_id"],
                }
                accepted.append(entry)
                audit.append({
                    "id": idx, "check_id": entry["check_id"],
                    "outcome": "accepted_corrected",
                    "corrected_to": better,
                })
            else:
                rejected.append({
                    "id": idx,
                    "check_id": entry["check_id"],
                    "original_capability_id": entry["expected_capability_id"],
                    "suggested_capability_id": better,
                    "comment": comment,
                    "reason": (
                        "external_llm_disagreed_and_no_valid_replacement"
                        if not better else
                        f"suggested_capability_id '{better}' not in catalog"
                    ),
                })
                audit.append({
                    "id": idx, "check_id": entry["check_id"],
                    "outcome": "rejected_disagree",
                })
        else:
            audit.append({"id": idx, "outcome": "skipped_unknown_verdict",
                          "verdict_raw": v.get("verdict")})

    # Merge accepted into golden_set
    golden["mappings"].extend(accepted)
    golden["version"] = golden.get("version", "1.0") + "+ext_review"
    golden["external_review"] = {
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "source_response": str(response_path),
        "accepted": len(accepted),
        "rejected": len(rejected),
    }

    _save_json(golden_path, golden)

    audit_payload = {
        "summary": {
            "verdicts_in_response": len(verdicts),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "skipped": sum(1 for a in audit if a["outcome"].startswith("skipped")),
        },
        "accepted_check_ids": [e["check_id"] for e in accepted],
        "rejected_entries": rejected,
        "decisions": audit,
    }
    _save_json(audit_path, audit_payload)

    return audit_payload["summary"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--response",
        required=True,
        type=Path,
        help="Path to the saved external LLM response (raw text or JSON)",
    )
    parser.add_argument(
        "--draft",
        default="RAG/pipeline/mapping/tier4_validation/golden_set_additions_draft.json",
        type=Path,
    )
    parser.add_argument(
        "--golden",
        default="RAG/pipeline/mapping/tier4_validation/golden_set.json",
        type=Path,
    )
    parser.add_argument(
        "--capabilities",
        default="RAG/data/normalized/maturity_capabilities.json",
        type=Path,
    )
    parser.add_argument(
        "--prowler",
        default="RAG/data/raw/prowler_checks.json",
        type=Path,
    )
    parser.add_argument(
        "--audit",
        default="RAG/pipeline/mapping/tier4_validation/external_review_audit.json",
        type=Path,
    )
    args = parser.parse_args()

    summary = merge(
        response_path=args.response,
        draft_path=args.draft,
        golden_path=args.golden,
        capabilities_path=args.capabilities,
        prowler_path=args.prowler,
        audit_path=args.audit,
    )
    print(json.dumps(summary, indent=2))
    print(f"\nGolden set updated:     {args.golden}")
    print(f"Audit log written to:   {args.audit}")


if __name__ == "__main__":
    main()
