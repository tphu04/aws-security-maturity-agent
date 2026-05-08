from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent
from pdca.agents.shared.callbacks import extract_config_callbacks, get_callbacks
from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph._tracing_helpers import (
    emit_score,
    flush_at_node,
    node_span,
    update_trace_metadata,
)
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def _severity_distribution(findings: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for f in findings or []:
        sev = str(f.get("ai_severity") or f.get("severity") or "unknown").lower()
        dist[sev] = dist.get(sev, 0) + 1
    return dist


def risk_eval_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    callbacks = get_callbacks(extra=extract_config_callbacks(config))
    metrics = state.get("performance_metrics", {})
    logger.info("risk_eval start", extra={"run_id": run_id})

    with node_span("risk_evaluation", run_id) as sp:
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
        sev_dist = _severity_distribution(prioritized)
        update_trace_metadata(**{"pdca.risk.severity_dist": sev_dist})
        sp.update(
            output={
                "prioritized_count": len(prioritized),
                "severity_dist": sev_dist,
            }
        )
        emit_score(run_id, "risk_severity_critical", float(sev_dist.get("critical", 0)))
        emit_score(run_id, "risk_severity_high", float(sev_dist.get("high", 0)))
        flush_at_node()

    logger.info(
        "risk_eval done",
        extra={"run_id": run_id, "prioritized_count": len(prioritized)},
    )
    return {"prioritized_findings": prioritized, "performance_metrics": metrics}
