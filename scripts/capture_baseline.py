"""Capture Phase-6 baseline artifacts for the 7 scenarios (A..G).

Runs :class:`ReportAgent` on each fixture with a deterministic mock LLM
and saves:

* ``tests/fixtures/report_baseline/input/{X}.json``          — fixture data
* ``tests/fixtures/report_baseline/output_after/{X}.html``   — rendered report
* ``tests/fixtures/report_baseline/validation_reports/{X}.json``
* ``tests/fixtures/report_baseline/metrics.json``            — aggregate metrics

The mock LLM returns a scope-safe Vietnamese response for every prompt
so the run is reproducible and the pipeline itself (scope detection,
validator, template rendering) is what's exercised end-to-end. The
fallback template still triggers for bypass paths (zero-findings,
all-pass).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fixtures.report_baseline.fixture_builder import ALL_BUILDERS  # noqa: E402
from pdca.agents.report_agent import ReportAgent  # noqa: E402

BASE = ROOT / "tests" / "fixtures" / "report_baseline"
INPUT = BASE / "input"
OUTPUT = BASE / "output_after"
VALIDATION = BASE / "validation_reports"
METRICS = BASE / "metrics.json"


class _Resp:
    def __init__(self, content: str):
        self.content = content


class SafeMockLLM:
    """Returns a scope-safe generic response regardless of prompt.

    The response avoids AWS service names and resource terms so it
    never triggers the Phase-5 validator — the captured HTML then
    reflects the LLM-path (not the fallback template) for scenarios
    where the agent does call the LLM.
    """
    SAFE_TEXT = (
        "Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. "
        "Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất "
        "phương án khắc phục phù hợp với mức độ ưu tiên."
    )

    def __init__(self):
        self.call_count = 0

    def invoke(self, messages):
        self.call_count += 1
        return _Resp(self.SAFE_TEXT)


def _ensure_clean(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_input_json(letter: str, data: Dict[str, Any]) -> Path:
    path = INPUT / f"{letter}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def _run_fixture(letter: str, data: Dict[str, Any]) -> Dict[str, Any]:
    work_dir = OUTPUT / letter
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    llm = SafeMockLLM()
    agent = ReportAgent(
        output_path=str(work_dir / "final_report.md"),
        llm_config={"llm": llm},
    )
    result = agent.run(data)

    html_src = Path(result["html"])
    html_dst = OUTPUT / f"{letter}.html"
    shutil.copy(html_src, html_dst)

    vreport_src = Path(result["validation_report"])
    vreport_dst = VALIDATION / f"{letter}.json"
    VALIDATION.mkdir(parents=True, exist_ok=True)
    shutil.copy(vreport_src, vreport_dst)

    with open(vreport_dst, encoding="utf-8") as f:
        vreport = json.load(f)

    return {
        "letter": letter,
        "llm_calls": llm.call_count,
        "html_bytes": html_dst.stat().st_size,
        "validation": vreport,
    }


def _scope_metrics(html: str, letter: str) -> Dict[str, Any]:
    import re
    lower = html.lower()
    return {
        "mentions_s3": bool(re.search(r"\bamazon s3\b", lower)),
        "mentions_bucket": "bucket" in lower,
        "mentions_iam": bool(re.search(r"\baws iam\b", lower)),
        "mentions_ec2": bool(re.search(r"\bamazon ec2\b", lower)),
        "mentions_infrastructure":
            "aws infrastructure" in lower,
        "html_bytes": len(html),
    }


def main() -> int:
    INPUT.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VALIDATION.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {"fixtures": {}}
    for letter, builder in ALL_BUILDERS.items():
        data = builder()
        _write_input_json(letter, data)
        result = _run_fixture(letter, data)
        html_path = OUTPUT / f"{letter}.html"
        html = html_path.read_text(encoding="utf-8")
        scope = _scope_metrics(html, letter)
        summary["fixtures"][letter] = {
            "llm_calls": result["llm_calls"],
            "validation_issue_count": result["validation"]["issue_count"],
            "validation_summary": result["validation"]["summary"],
            "scope": scope,
        }
        print(f"[{letter}] llm={result['llm_calls']} "
              f"issues={result['validation']['issue_count']} "
              f"html={scope['html_bytes']}B")

    with open(METRICS, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nMetrics written to: {METRICS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
