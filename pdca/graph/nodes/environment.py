from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.environment_agent import EnvironmentAgent
from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph._tracing_helpers import flush_at_node, node_span, update_trace_metadata
from pdca.graph.state import PDCAState
from pdca.observability.redaction import safe_redact

logger = logging.getLogger(__name__)


def environment_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    metrics = state.get(
        "performance_metrics",
        {"step_duration": {}, "llm_latency": {}, "system_info": {}},
    )

    logger.info("environment_node start", extra={"run_id": run_id})
    with node_span("environment", run_id) as sp:
        with measure_time() as timer:
            ctx = EnvironmentAgent().get_aws_context()

        rag_client = RAGClient(base_url=settings.rag_api_url, timeout=3.0)
        rag_available = rag_client.is_healthy()

        metrics = update_metrics(metrics, "step_duration", "environment_setup", timer())
        update_trace_metadata(
            **{
                "aws.account_id_redacted": safe_redact(ctx.get("account_id")),
                "aws.region": ctx.get("region"),
                "rag_available": rag_available,
            }
        )
        sp.update(
            output={
                "rag_available": rag_available,
                "buckets_count": len(ctx.get("buckets") or []),
                "degraded": bool(ctx.get("_degraded")),
            }
        )
        flush_at_node()

    logger.info(
        "environment_node done",
        extra={
            "run_id": run_id,
            "account_id": ctx.get("account_id"),
            "rag_available": rag_available,
        },
    )
    return {
        "aws_context": ctx,
        "rag_available": rag_available,
        "performance_metrics": metrics,
    }
