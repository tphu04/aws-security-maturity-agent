from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.resolve import router as resolve_router
from app.api.routes.retrieve import router as retrieve_router
from app.core.config import (
    BM25_INDEX_PATHS,
    CHROMA_DIR,
    MANIFEST_PATH,
    SERVICE_NAME,
    SERVICE_VERSION,
    CORPUS_PROWLER_CHECKS,
    CORPUS_MATURITY_CAPABILITIES,
)
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex
from app.retrieval.pipeline import RetrievalPipeline
from app.services.check_service import CheckService
from app.services.context_service import ContextService
from app.services.mapping_service import MappingService
from app.services.maturity_service import MaturityService
from app.services.report_context_service import ReportContextService


def _load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        try:
            with MANIFEST_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _build_services() -> Dict[str, Any]:
    lexical_indexes: Dict[str, BM25Index] = {}
    vector_index: Optional[VectorIndex] = None

    # Load BM25 if available
    for corpus, path in BM25_INDEX_PATHS.items():
        if Path(path).exists():
            lexical_indexes[corpus] = BM25Index.load(path)

    # Vector index is optional. Fail open for lexical-only mode.
    try:
        chroma_dir = Path(CHROMA_DIR)
        if chroma_dir.exists():
            vector_index = VectorIndex(persist_dir=chroma_dir)
    except Exception:
        vector_index = None

    retrieval_pipeline = RetrievalPipeline(
        lexical_indexes=lexical_indexes,
        vector_index=vector_index,
    )

    check_service = CheckService(pipeline=retrieval_pipeline)
    maturity_service = MaturityService(pipeline=retrieval_pipeline)
    mapping_service = MappingService()
    context_service = ContextService(
        check_service=check_service,
        mapping_service=mapping_service,
        maturity_service=maturity_service,
        pipeline=retrieval_pipeline,
    )

    report_context_service = ReportContextService(
        context_service=context_service,
        maturity_service=maturity_service,
    )

    return {
        "lexical_index": lexical_indexes,
        "vector_index": vector_index,
        "retrieval_pipeline": retrieval_pipeline,
        "check_service": check_service,
        "maturity_service": maturity_service,
        "mapping_service": mapping_service,
        "context_service": context_service,
        "report_context_service": report_context_service,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.app_initialized = False
    app.state.build_info = _load_manifest()

    services = _build_services()
    for key, value in services.items():
        setattr(app.state, key, value)

    app.state.app_initialized = True
    yield


def _cors_settings() -> tuple[list[str], bool]:
    """Read CORS config from env (RAG service is standalone — no pdca import).

    `CORS_ORIGINS` is a JSON list (e.g. `["*"]`) or comma-separated string.
    Wildcard origin forces `allow_credentials=False` (CORS spec — see Phase A2).
    """
    import os as _os

    raw = _os.getenv("CORS_ORIGINS", '["*"]').strip()
    try:
        origins = json.loads(raw)
        if not isinstance(origins, list):
            raise ValueError
    except Exception:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
    allow_credentials = _os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
    if "*" in origins and allow_credentials:
        allow_credentials = False
    return origins, allow_credentials


_cors_origins, _cors_credentials = _cors_settings()

app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="RAG retrieval service for AWS assessment context building.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(retrieve_router)
app.include_router(resolve_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn
    from pathlib import Path as _Path

    _app_dir = _Path(__file__).resolve().parent
    print("Starting RAG service (auto-reload enabled)...")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=9005,
        reload=True,
        reload_dirs=[str(_app_dir)],
    )