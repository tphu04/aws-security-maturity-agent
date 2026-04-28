from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.report_agent import ReportAgent
from pdca.agents.report_module.data_builder import ReportDataBuilder
from pdca.agents.shared.callbacks import get_callbacks
from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._metrics import (
    measure_time,
    save_performance_metrics,
    update_metrics,
)
from pdca.graph._tracing_helpers import (
    emit_score,
    flush_at_node,
    node_span,
    update_trace_metadata,
)
from pdca.graph.state import PDCAState
from pdca.observability.tracing import span as obs_span

logger = logging.getLogger(__name__)


def _outcome_tag(state: PDCAState) -> str:
    if state.get("aws_context", {}).get("_degraded"):
        return "degraded"
    errors = state.get("errors") or []
    if errors:
        return "partial_failure"
    return "success"


def report_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    extra_callbacks = (
        config.get("callbacks")
        or config.get("configurable", {}).get("callbacks", [])
        or []
    )
    callbacks = get_callbacks(extra=list(extra_callbacks))
    metrics = state.get("performance_metrics", {})
    logger.info("report start", extra={"run_id": run_id})

    node_ctx = node_span("report", run_id)
    sp = node_ctx.__enter__()
    try:
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
        with obs_span("maturity:assess") as maturity_sp:
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
                maturity_sp.update(
                    output={
                        "score": maturity_pre.get("overall_score") if maturity_pre else None,
                        "has_post": bool(raw_post),
                    }
                )
            except Exception as e:
                logger.warning(
                    "maturity assessment failed",
                    extra={"run_id": run_id, "error": str(e)},
                )
                maturity_sp.set_status("error", str(e))
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

        validation_issues = list(getattr(agent, "_validation_issues", []) or [])
        outcome_tag = _outcome_tag(state)
        update_trace_metadata(**{"pdca.outcome.tag": outcome_tag})
        sp.update(
            output={
                "report_path": path if isinstance(path, str) else None,
                "validation_issues": len(validation_issues),
                "outcome": outcome_tag,
            }
        )
        emit_score(
            run_id,
            "validation_issues",
            float(len(validation_issues)),
            comment=f"outcome={outcome_tag}",
        )
        flush_at_node()
    except BaseException as exc:
        node_ctx.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        node_ctx.__exit__(None, None, None)

    logger.info("report done", extra={"run_id": run_id, "path": path})
    return {"final_report": path, "performance_metrics": metrics}
