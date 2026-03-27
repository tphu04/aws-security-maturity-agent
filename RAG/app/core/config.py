import json
from pathlib import Path
from typing import Any, Dict


class Settings:
    service_name = "rag-service"
    service_version = "1.0.0"


settings = Settings()

SERVICE_NAME = settings.service_name
SERVICE_VERSION = settings.service_version

# -------------------------------------------------------------------
# Core configuration
# -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_ROOT = PROJECT_ROOT / "data"
RAW_DIR = DATA_ROOT / "raw"
NORMALIZED_DIR = DATA_ROOT / "normalized"
INDEX_DIR = DATA_ROOT / "indexes"
BENCHMARK_DIR = DATA_ROOT / "benchmarks"

# -------------------------------------------------------------------
# Raw source files
# -------------------------------------------------------------------
PROWLER_RAW_PATH = RAW_DIR / "prowler_checks.json"
MATURITY_RAW_PATH = RAW_DIR / "maturity_capabilities.json"
MAPPINGS_RAW_PATH = RAW_DIR / "maturity_mappings.json"
MAPPINGS_CURATED_PATH = RAW_DIR / "maturity_mappings_curated.json"

# -------------------------------------------------------------------
# Versioning / models
# -------------------------------------------------------------------
INDEX_VERSION = "rag-v2-2026-03-17"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# -------------------------------------------------------------------
# Corpus registry
# -------------------------------------------------------------------
CORPUS_PROWLER_CHECKS = "prowler_checks"
CORPUS_MATURITY_CAPABILITIES = "maturity_capabilities"
CORPUS_MATURITY_MAPPINGS = "maturity_mappings"

SUPPORTED_CORPORA = (
    CORPUS_PROWLER_CHECKS,
    CORPUS_MATURITY_CAPABILITIES,
    CORPUS_MATURITY_MAPPINGS,
)

# -------------------------------------------------------------------
# Normalized artifacts
# -------------------------------------------------------------------
NORMALIZED_PATHS = {
    CORPUS_PROWLER_CHECKS: NORMALIZED_DIR / "prowler_checks.json",
    CORPUS_MATURITY_CAPABILITIES: NORMALIZED_DIR / "maturity_capabilities.json",
    CORPUS_MATURITY_MAPPINGS: NORMALIZED_DIR / "maturity_mappings.json",
}

# -------------------------------------------------------------------
# BM25 storage
# -------------------------------------------------------------------
BM25_DIR = INDEX_DIR / "bm25"

BM25_INDEX_PATHS = {
    CORPUS_PROWLER_CHECKS: BM25_DIR / "bm25_prowler_checks.pkl",
    CORPUS_MATURITY_CAPABILITIES: BM25_DIR / "bm25_maturity_capabilities.pkl",
    CORPUS_MATURITY_MAPPINGS: BM25_DIR / "bm25_maturity_mappings.pkl",
}

# -------------------------------------------------------------------
# Chroma storage
# -------------------------------------------------------------------
CHROMA_DIR = INDEX_DIR / "chroma"

CHROMA_COLLECTIONS = {
    CORPUS_PROWLER_CHECKS: CORPUS_PROWLER_CHECKS,
    CORPUS_MATURITY_CAPABILITIES: CORPUS_MATURITY_CAPABILITIES,
    CORPUS_MATURITY_MAPPINGS: CORPUS_MATURITY_MAPPINGS,
}

# Legacy monolithic collection name để migration/cleanup
LEGACY_CHROMA_COLLECTION = "rag_docs"

# -------------------------------------------------------------------
# Manifest
# -------------------------------------------------------------------
MANIFEST_PATH = INDEX_DIR / "manifest.json"

# -------------------------------------------------------------------
# Mapping quality gate
# -------------------------------------------------------------------
MAPPING_MIN_SCORE = 0.25
MAPPING_MIN_SCORE_GAP = 0.05

# -------------------------------------------------------------------
# BM25 parameters (tuned for shorter retrieval texts after Slice 2)
# -------------------------------------------------------------------
BM25_K1 = 1.2   # term frequency saturation (lower = less saturation)
BM25_B = 0.6    # document length normalization (lower = less penalty for short docs)

# -------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------
DEFAULT_TOP_K = 5
DEFAULT_TIMEOUT_MS = 1500

# -------------------------------------------------------------------
# Allowed filters
# -------------------------------------------------------------------
ALLOWED_FILTERS = {
    "doc_type",
    "provider",
    "service",
    "domain",
    "capability_id",
    "check_id",
}

# -------------------------------------------------------------------
# Scoring configuration (externalized from pipeline.py / confidence.py / verifier.py)
# -------------------------------------------------------------------
SCORING_CONFIG_PATH = Path(__file__).resolve().parent / "scoring_config.json"

_scoring_config_cache: Dict[str, Any] | None = None


def load_scoring_config() -> Dict[str, Any]:
    """Load scoring config from JSON file with fallback defaults.

    Config is cached after first load. To reload after file change,
    call ``reload_scoring_config()``.
    """
    global _scoring_config_cache
    if _scoring_config_cache is not None:
        return _scoring_config_cache

    defaults: Dict[str, Any] = {
        "rrf": {"k": 60},
        "exact_match_bonus": 2.0,
        "metadata_bonus": {
            "service_match": 0.03,
            "domain_match": 0.02,
        },
        "reranker": {
            "enabled": True,
            "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "top_n": 20,
        },
        "product_gate": "filter",
        "search_top_k_multiplier": 3,
        "search_top_k_minimum": 10,
        "confidence_thresholds": {
            "mapping_resolution": {"high": 0.99},
            "check_search": {"high": 0.70, "medium": 0.35},
            "maturity_search": {"high": 0.60, "medium": 0.30},
            "default": {"high": 0.65, "medium": 0.30},
        },
        "ambiguity": {
            "gap_high_to_medium": 0.10,
            "gap_to_low": 0.03,
        },
        "verification": {
            "ambiguity_threshold": 0.05,
            "low_score_threshold": 0.15,
        },
    }

    if SCORING_CONFIG_PATH.exists():
        try:
            with SCORING_CONFIG_PATH.open("r", encoding="utf-8") as f:
                file_config = json.load(f)
            # Deep merge: file values override defaults
            _deep_merge(defaults, file_config)
        except Exception:
            pass  # fallback to defaults silently

    _scoring_config_cache = defaults
    return _scoring_config_cache


def reload_scoring_config() -> Dict[str, Any]:
    """Force reload scoring config from disk (e.g. after editing the JSON)."""
    global _scoring_config_cache
    _scoring_config_cache = None
    return load_scoring_config()


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Recursively merge *override* into *base* in place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
