from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent
from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def risk_eval_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    callbacks = (
        config.get("callbacks")
        or config.get("configurable", {}).get("callbacks", [])
        or []
    )
    metrics = state.get("performance_metrics", {})
    logger.info("risk_eval start", extra={"run_id": run_id})

    rag_client = RAGClient(base_url=settings.rag_api_url)
    risk_agent = RiskEvaluationAgent(
        settings.ollama_model,
        settings.ollama_api_key,
        settings.ollama_base_url,
        rag_client=rag_client,
        callbacks=callbacks,
    )

    findings = state.get("normalized_findings") or state.get("raw_findings", [])

    with measure_time() as timer:
        prioritized = risk_agent.run(findings)

    llm_metrics = risk_agent.get_llm_metrics()
    metrics = update_metrics(metrics, "step_duration", "risk_evaluation_node", timer())
    metrics = update_metrics(
        metrics, "llm_latency", "risk_evaluation_agent", llm_metrics
    )
    logger.info(
        "risk_eval done",
        extra={"run_id": run_id, "prioritized_count": len(prioritized)},
    )
    return {"prioritized_findings": prioritized, "performance_metrics": metrics}
