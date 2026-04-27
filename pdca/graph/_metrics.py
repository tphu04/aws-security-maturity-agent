"""Shared metrics helpers for graph nodes (extracted from orchestrator)."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from typing import Any, Dict


@contextmanager
def measure_time():
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start


def update_metrics(current_metrics: Dict, category: str, key: str, value: Any) -> Dict:
    if current_metrics is None:
        current_metrics = {"step_duration": {}, "llm_latency": {}, "system_info": {}}
    if category not in current_metrics:
        current_metrics[category] = {}
    if isinstance(value, float):
        current_metrics[category][key] = round(value, 4)
    else:
        current_metrics[category][key] = value
    return current_metrics


def save_performance_metrics(
    metrics: Dict[str, Any], path: str = "data/artifacts/performance_metrics.json"
) -> None:
    try:
        start_time = metrics.get("system_info", {}).get("start_time")
        if start_time:
            metrics["system_info"]["total_duration"] = round(
                time.time() - start_time, 2
            )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
    except Exception:
        # Metrics persistence is best-effort — failure must not break the run.
        pass


def save_scan_configuration(
    plan_data: Dict[str, Any],
    path: str = "data/artifacts/initial_scan_config.json",
) -> None:
    """Persist plan để RescanAgent dùng lại ở verification (legacy file path)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        config_data = {
            "groups_to_scan": plan_data.get("groups_to_scan", []),
            "checks_to_scan": plan_data.get("checks_to_scan", []),
            "reasoning": plan_data.get("reasoning", ""),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
