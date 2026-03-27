"""
Build pipeline for RAG service.

This script is responsible for:
- loading raw source snapshots
- normalizing documents into spec schemas
- persisting normalized artifacts per corpus
- building BM25 lexical indexes per corpus
- building Chroma vector collections per corpus
- generating a manifest as the source of truth for runtime loading
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from app.core.config import (
    CHROMA_COLLECTIONS,
    CORPUS_MATURITY_CAPABILITIES,
    CORPUS_MATURITY_MAPPINGS,
    CORPUS_PROWLER_CHECKS,
    DATA_ROOT,
    EMBEDDING_MODEL,
    INDEX_DIR,
    INDEX_VERSION,
    MANIFEST_PATH,
    MAPPINGS_CURATED_PATH,
    NORMALIZED_PATHS,
    SUPPORTED_CORPORA,
    BM25_INDEX_PATHS,
)
from app.ingestion.loaders import (
    load_mappings_raw,
    load_maturity_raw,
    load_prowler_raw,
)
from app.ingestion.normalizers import (
    build_capability_name_to_id_lookup,
    normalize_mapping_doc,
    normalize_maturity_doc,
    normalize_prowler_doc,
)
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex


def _generate_maturity_mappings() -> None:
    script_path = Path(__file__).resolve().parent / "gen_maturity_mapping.py"
    if not script_path.exists():
        raise FileNotFoundError(f"missing mapping generator: {script_path}")

    print("[build_all] Generating maturity mappings...")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(script_path.parent.parent),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(
            f"maturity mapping generation failed with exit code {result.returncode}"
        )


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fallback_build_text(doc: Dict[str, Any]) -> str:
    """
    Fallback only.
    Primary text for lexical/vector should come from normalized doc['retrieval_text'].
    """
    parts: List[str] = []
    doc_type = doc.get("doc_type")

    if doc_type == "prowler_check":
        parts.extend(
            [
                str(doc.get("check_id", "")),
                str(doc.get("service", "")),
                str(doc.get("title", "")),
                str(doc.get("description", "")),
                str(doc.get("risk", "")),
                str(doc.get("remediation", "")),
                " ".join(doc.get("keywords", []) or []),
                " ".join(doc.get("tags", []) or []),
            ]
        )
    elif doc_type == "maturity_capability":
        parts.extend(
            [
                str(doc.get("capability_id", "")),
                str(doc.get("capability_name", "")),
                str(doc.get("domain", "")),
                str(doc.get("summary", "")),
                str(doc.get("risk_explanation", "")),
                str(doc.get("guidance", "")),
                str(doc.get("how_to_check", "")),
                " ".join(doc.get("recommended_practices", []) or []),
                " ".join(doc.get("keywords", []) or []),
                " ".join(doc.get("tags", []) or []),
            ]
        )
    elif doc_type == "maturity_mapping":
        parts.extend(
            [
                str(doc.get("check_id", "")),
                str(doc.get("service", "")),
                str(doc.get("domain", "")),
                str(doc.get("capability_id", "")),
                str(doc.get("capability_name", "")),
                str(doc.get("mapping_reason", "")),
                str(doc.get("mapping_type", "")),
                str(doc.get("mapping_confidence", "")),
                " ".join(doc.get("tags", []) or []),
            ]
        )
    else:
        for value in doc.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.append(" ".join(str(x) for x in value if x is not None))

    return "\n".join([p for p in parts if str(p).strip()])


def _document_text(doc: Dict[str, Any]) -> str:
    retrieval_text = str(doc.get("retrieval_text", "") or "").strip()
    if retrieval_text:
        return retrieval_text
    return _fallback_build_text(doc)


def _to_index_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc_id = doc.get("doc_id")
    if not doc_id:
        raise ValueError("normalized doc missing doc_id")

    return {
        "doc_id": str(doc_id),
        "text": _document_text(doc),
        "metadata": {
            "doc_type": doc.get("doc_type"),
            "provider": doc.get("provider"),
            "service": doc.get("service"),
            "domain": doc.get("domain"),
            "capability_id": doc.get("capability_id"),
            "check_id": doc.get("check_id"),
            "index_version": doc.get("index_version"),
            "source_name": doc.get("source_name"),
            "source_type": doc.get("source_type"),
        },
    }


def _validate_unique_doc_ids(corpus_name: str, docs: Iterable[Dict[str, Any]]) -> None:
    seen: Dict[str, int] = {}
    duplicates: List[str] = []

    for doc in docs:
        doc_id = str(doc.get("doc_id", "") or "").strip()
        if not doc_id:
            raise ValueError(f"missing doc_id in corpus '{corpus_name}'")
        seen[doc_id] = seen.get(doc_id, 0) + 1
        if seen[doc_id] == 2:
            duplicates.append(doc_id)

    if duplicates:
        preview = ", ".join(sorted(duplicates[:10]))
        raise ValueError(
            f"duplicate doc_id detected in corpus '{corpus_name}': {preview}"
        )


def _load_curated_mappings() -> List[Dict[str, Any]]:
    """Load curated mappings if file exists. Curated mappings take priority over generated."""
    if not MAPPINGS_CURATED_PATH.exists():
        print("[build_all] No curated mappings found, using generated only.")
        return []

    with MAPPINGS_CURATED_PATH.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    print(f"[build_all] Loaded {len(items)} curated mappings from {MAPPINGS_CURATED_PATH}")
    return items


def _normalize_key(value: str) -> str:
    """Normalize a mapping key for comparison: lowercase, strip, replace - with _."""
    import re
    text = str(value).strip().lower()
    text = text.replace("-", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    # Strip common prefixes from auto-generated capability_ids
    text = re.sub(r"^\d+_(quickwins|quick_wins|foundational|efficient|optimized)_", "", text)
    return text


def _merge_mappings(
    generated: List[Dict[str, Any]],
    curated: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge curated + generated mappings. Curated override generated for same check_id."""
    # Index curated by check_id (each curated check_id overrides generated for that check)
    curated_check_ids: set = set()
    merged: List[Dict[str, Any]] = []

    for item in curated:
        check_id = _normalize_key(item.get("check_id", ""))
        if check_id:
            curated_check_ids.add(check_id)
            merged.append(item)

    # Add generated only if check_id not covered by curated
    overridden = 0
    for item in generated:
        check_id = _normalize_key(item.get("check_id", ""))
        if check_id in curated_check_ids:
            overridden += 1
            continue
        merged.append(item)

    print(
        f"[build_all] Merged mappings: {len(curated)} curated + "
        f"{len(generated) - overridden} generated ({overridden} overridden by curated) = {len(merged)} total"
    )
    return merged


def _normalize_all() -> (
    Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]
):
    prowler_raw = load_prowler_raw()
    maturity_raw = load_maturity_raw()
    mapping_raw = load_mappings_raw()

    # Load curated mappings (if any)
    curated_raw = _load_curated_mappings()

    # Merge curated + generated: curated takes priority
    merged_mapping_raw = _merge_mappings(mapping_raw, curated_raw)

    # Normalize capabilities first -> this corpus is the source of truth
    # for canonical capability_id values.
    prowler_normalized = [normalize_prowler_doc(r).model_dump() for r in prowler_raw]

    maturity_docs = [normalize_maturity_doc(r) for r in maturity_raw]
    capability_lookup = build_capability_name_to_id_lookup(maturity_docs)
    maturity_normalized = [doc.model_dump() for doc in maturity_docs]

    # Normalize mappings second, using canonical capability ids from capabilities.
    mapping_normalized = [
        normalize_mapping_doc(r, capability_lookup=capability_lookup).model_dump()
        for r in merged_mapping_raw
    ]

    return prowler_normalized, maturity_normalized, mapping_normalized


def _build_bm25_for_corpus(corpus_name: str, docs: List[Dict[str, Any]]) -> Path:
    from app.core.config import BM25_K1, BM25_B
    bm25 = BM25Index(k1=BM25_K1, b=BM25_B)
    bm25.add_documents(docs)
    output_path = BM25_INDEX_PATHS[corpus_name]
    _ensure_dir(output_path.parent)
    bm25.save(output_path)
    return output_path


def _build_vector_for_corpus(
    vector: VectorIndex, corpus_name: str, docs: List[Dict[str, Any]]
) -> str:
    collection_name = CHROMA_COLLECTIONS[corpus_name]
    vector.build_collection(name=collection_name, docs=docs)
    return collection_name


def _cleanup_orphaned_collections(vector: VectorIndex) -> None:
    """Remove all Chroma collections that are not in CHROMA_COLLECTIONS config."""
    try:
        active_names = set(CHROMA_COLLECTIONS.values())
        all_collections = vector.client.list_collections()
        removed = 0
        for col in all_collections:
            col_name = col if isinstance(col, str) else getattr(col, "name", str(col))
            if col_name not in active_names:
                vector.delete_collection(col_name)
                removed += 1
        if removed:
            print(f"[build_all] Cleaned up {removed} orphaned collection(s)")
        else:
            print("[build_all] No orphaned collections found")
    except Exception as exc:
        print(f"[build_all] Orphaned collection cleanup skipped: {exc}")


def main() -> None:
    print("[build_all] Starting clean multi-corpus RAG build...")

    _ensure_dir(DATA_ROOT / "normalized")
    _ensure_dir(INDEX_DIR)

    # 0) Generate maturity mappings so build_all is self-contained.
    _generate_maturity_mappings()

    # 1) Normalize all corpora
    prowler_normalized, maturity_normalized, mapping_normalized = _normalize_all()

    corpus_docs: Dict[str, List[Dict[str, Any]]] = {
        CORPUS_PROWLER_CHECKS: prowler_normalized,
        CORPUS_MATURITY_CAPABILITIES: maturity_normalized,
        CORPUS_MATURITY_MAPPINGS: mapping_normalized,
    }

    # 2) Validate document integrity before persisting/building
    for corpus_name, docs in corpus_docs.items():
        _validate_unique_doc_ids(corpus_name, docs)

    # 3) Persist normalized artifacts
    for corpus_name, docs in corpus_docs.items():
        _write_json(NORMALIZED_PATHS[corpus_name], docs)
        print(
            f"[build_all] Wrote normalized artifact: "
            f"{NORMALIZED_PATHS[corpus_name]} ({len(docs)} docs)"
        )

    # 4) Convert each corpus into index payload docs
    index_docs_by_corpus: Dict[str, List[Dict[str, Any]]] = {}
    for corpus_name, docs in corpus_docs.items():
        index_docs_by_corpus[corpus_name] = [_to_index_doc(doc) for doc in docs]

    # 5) Build BM25 per corpus
    bm25_outputs: Dict[str, str] = {}
    for corpus_name in SUPPORTED_CORPORA:
        output_path = _build_bm25_for_corpus(
            corpus_name, index_docs_by_corpus[corpus_name]
        )
        bm25_outputs[corpus_name] = str(output_path)
        print(
            f"[build_all] Built BM25 for {corpus_name}: "
            f"{output_path} ({len(index_docs_by_corpus[corpus_name])} docs)"
        )

    # 6) Build vector collections per corpus
    vector_outputs: Dict[str, str] = {}
    vector_error: str | None = None
    try:
        vector = VectorIndex()
        for corpus_name in SUPPORTED_CORPORA:
            collection_name = _build_vector_for_corpus(
                vector=vector,
                corpus_name=corpus_name,
                docs=index_docs_by_corpus[corpus_name],
            )
            vector_outputs[corpus_name] = collection_name
            print(
                f"[build_all] Built vector collection for {corpus_name}: "
                f"{collection_name} ({len(index_docs_by_corpus[corpus_name])} docs)"
            )

        _cleanup_orphaned_collections(vector)
    except Exception as exc:
        vector_error = str(exc)
        print(f"[build_all] Vector build skipped/failed: {exc}")

    # 7) Write manifest
    manifest = {
        "index_version": INDEX_VERSION,
        "built_at": _utc_now_iso(),
        "embedding_model": EMBEDDING_MODEL,
        "storage_layout": "multi_corpus",
        "corpora": {
            CORPUS_PROWLER_CHECKS: {
                "normalized_path": str(NORMALIZED_PATHS[CORPUS_PROWLER_CHECKS]),
                "bm25_path": bm25_outputs.get(CORPUS_PROWLER_CHECKS),
                "chroma_collection": CHROMA_COLLECTIONS[CORPUS_PROWLER_CHECKS],
                "doc_count": len(corpus_docs[CORPUS_PROWLER_CHECKS]),
                "doc_type": "prowler_check",
            },
            CORPUS_MATURITY_CAPABILITIES: {
                "normalized_path": str(NORMALIZED_PATHS[CORPUS_MATURITY_CAPABILITIES]),
                "bm25_path": bm25_outputs.get(CORPUS_MATURITY_CAPABILITIES),
                "chroma_collection": CHROMA_COLLECTIONS[CORPUS_MATURITY_CAPABILITIES],
                "doc_count": len(corpus_docs[CORPUS_MATURITY_CAPABILITIES]),
                "doc_type": "maturity_capability",
            },
            CORPUS_MATURITY_MAPPINGS: {
                "normalized_path": str(NORMALIZED_PATHS[CORPUS_MATURITY_MAPPINGS]),
                "bm25_path": bm25_outputs.get(CORPUS_MATURITY_MAPPINGS),
                "chroma_collection": CHROMA_COLLECTIONS[CORPUS_MATURITY_MAPPINGS],
                "doc_count": len(corpus_docs[CORPUS_MATURITY_MAPPINGS]),
                "doc_type": "maturity_mapping",
            },
        },
        "counts": {
            "prowler_checks": len(corpus_docs[CORPUS_PROWLER_CHECKS]),
            "maturity_capabilities": len(corpus_docs[CORPUS_MATURITY_CAPABILITIES]),
            "maturity_mappings": len(corpus_docs[CORPUS_MATURITY_MAPPINGS]),
            "total": sum(len(v) for v in corpus_docs.values()),
        },
        "vector": {
            "persist_dir": str(INDEX_DIR / "chroma"),
            "collections": vector_outputs,
            "error": vector_error,
        },
        "cleanup": {
            "orphaned_collections_removed": True,
        },
    }

    _write_json(MANIFEST_PATH, manifest)
    print(f"[build_all] Wrote manifest: {MANIFEST_PATH}")
    print("[build_all] Build completed successfully.")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
