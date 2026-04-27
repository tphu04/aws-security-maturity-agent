from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.environment_agent import EnvironmentAgent
from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def environment_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    metrics = state.get(
        "performance_metrics",
        {"step_duration": {}, "llm_latency": {}, "system_info": {}},
    )

    logger.info("environment_node start", extra={"run_id": run_id})
    with measure_time() as timer:
        ctx = EnvironmentAgent().get_aws_context()

    rag_client = RAGClient(base_url=settings.rag_api_url, timeout=3.0)
    rag_available = rag_client.is_healthy()

    metrics = update_metrics(metrics, "step_duration", "environment_setup", timer())
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
