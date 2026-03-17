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
    LEGACY_CHROMA_COLLECTION,
    MANIFEST_PATH,
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
    normalize_mapping_doc,
    normalize_maturity_doc,
    normalize_prowler_doc,
)
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex


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


def _normalize_all() -> (
    Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]
):
    prowler_raw = load_prowler_raw()
    maturity_raw = load_maturity_raw()
    mapping_raw = load_mappings_raw()

    prowler_normalized = [normalize_prowler_doc(r).model_dump() for r in prowler_raw]
    maturity_normalized = [normalize_maturity_doc(r).model_dump() for r in maturity_raw]
    mapping_normalized = [normalize_mapping_doc(r).model_dump() for r in mapping_raw]

    return prowler_normalized, maturity_normalized, mapping_normalized


def _build_bm25_for_corpus(corpus_name: str, docs: List[Dict[str, Any]]) -> Path:
    bm25 = BM25Index()
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


def _cleanup_legacy_vector_collection() -> None:
    try:
        vector = VectorIndex()
        vector.delete_collection(LEGACY_CHROMA_COLLECTION)
        print(f"[build_all] Deleted legacy collection: {LEGACY_CHROMA_COLLECTION}")
    except Exception as exc:
        print(f"[build_all] Legacy collection cleanup skipped: {exc}")


def main() -> None:
    print("[build_all] Starting clean multi-corpus RAG build...")

    _ensure_dir(DATA_ROOT / "normalized")
    _ensure_dir(INDEX_DIR)

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

        _cleanup_legacy_vector_collection()
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
        "legacy_cleanup": {
            "removed_collection": LEGACY_CHROMA_COLLECTION,
        },
    }

    _write_json(MANIFEST_PATH, manifest)
    print(f"[build_all] Wrote manifest: {MANIFEST_PATH}")
    print("[build_all] Build completed successfully.")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
