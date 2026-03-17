from pathlib import Path


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

# -------------------------------------------------------------------
# Versioning / models
# -------------------------------------------------------------------
INDEX_VERSION = "rag-v2-2026-03-17"
EMBEDDING_MODEL = "intfloat/multilingual-e5-base"

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
