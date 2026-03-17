from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI

from app.api.routes.build import router as build_router
from app.api.routes.health import router as health_router
from app.api.routes.resolve import router as resolve_router
from app.api.routes.retrieve import router as retrieve_router
from app.core.config import (
    BM25_INDEX_PATHS,
    CHROMA_DIR,
    INDEX_DIR,
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


def _load_manifest() -> Dict[str, Any]:
    manifest_candidates = [
        Path(INDEX_DIR) / "manifest.json",
        Path(
            getattr(
                __import__("app.core.config", fromlist=["MANIFEST_PATH"]),
                "MANIFEST_PATH",
                "",
            )
        ),
    ]

    for candidate in manifest_candidates:
        if candidate and str(candidate).strip() and Path(candidate).exists():
            try:
                with Path(candidate).open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue

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

    return {
        "lexical_index": lexical_indexes,
        "vector_index": vector_index,
        "retrieval_pipeline": retrieval_pipeline,
        "check_service": check_service,
        "maturity_service": maturity_service,
        "mapping_service": mapping_service,
        "context_service": context_service,
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


app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description="RAG retrieval service for AWS assessment context building.",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(retrieve_router)
app.include_router(resolve_router)
app.include_router(build_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "running",
    }
