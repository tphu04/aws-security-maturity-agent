from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.report_agent import ReportAgent
from pdca.agents.report_module.data_builder import ReportDataBuilder
from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._metrics import (
    measure_time,
    save_performance_metrics,
    update_metrics,
)
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def report_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    callbacks = (
        config.get("callbacks")
        or config.get("configurable", {}).get("callbacks", [])
        or []
    )
    metrics = state.get("performance_metrics", {})
    logger.info("report start", extra={"run_id": run_id})

    rag_client = None
    if state.get("rag_available", False):
        rag_client = RAGClient(
            base_url=settings.rag_api_url, timeout=30.0, max_retries=2
        )

    findings_for_report = (
        state.get("normalized_findings") or state.get("raw_findings", []) or []
    )

    report_data = ReportDataBuilder.build(
        state_data={
            "analysis_results": state.get("analysis_results"),
            "raw_findings": findings_for_report,
            "aws_context": state.get("aws_context") or {},
            "assessment_plan": state.get("assessment_plan") or {},
            "user_request": state.get("user_request", ""),
        },
        rag_client=rag_client,
    )

    # --- Maturity Assessment (best-effort) ---
    try:
        from pdca.agents.report_module.maturity_engine import MaturityEngine

        engine = MaturityEngine(
            mappings_path="RAG/data/normalized/maturity_mappings.json",
            capabilities_path="RAG/data/normalized/maturity_capabilities.json",
        )
        scanned_services = report_data.get("scope", {}).get("services", [])
        maturity_pre = engine.assess(
            report_data.get("raw_pre_findings", []),
            scanned_services=scanned_services,
        )
        report_data["maturity_assessment"] = maturity_pre

        raw_post = report_data.get("raw_post_findings")
        if raw_post:
            maturity_post = engine.assess(raw_post, scanned_services=scanned_services)
            report_data["maturity_post"] = maturity_post
            report_data["maturity_delta"] = engine.compute_delta(
                maturity_pre, maturity_post
            )
        else:
            report_data["maturity_post"] = None
            report_data["maturity_delta"] = None
    except Exception as e:
        logger.warning(
            "maturity assessment failed",
            extra={"run_id": run_id, "error": str(e)},
        )
        report_data["maturity_assessment"] = None
        report_data["maturity_post"] = None
        report_data["maturity_delta"] = None

    agent = ReportAgent(
        settings.ollama_model,
        settings.ollama_api_key,
        settings.ollama_base_url,
        output_path="data/artifacts/final_report.md",
        callbacks=callbacks,
    )

    with measure_time() as timer:
        path = agent.run(report_context=report_data)

    llm_metrics = agent.get_llm_metrics()
    metrics = update_metrics(metrics, "step_duration", "report_node", timer())
    metrics = update_metrics(metrics, "llm_latency", "report_agent", llm_metrics)
    save_performance_metrics(metrics)

    logger.info("report done", extra={"run_id": run_id, "path": path})
    return {"final_report": path, "performance_metrics": metrics}
