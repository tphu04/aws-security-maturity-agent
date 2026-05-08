"""D0 — Export per-run signals from Langfuse for downstream aggregation.

Reusable across D1 (timing) / D5 (HITL) / D6 (token cost). Pulls observations
for each PDCA run via the Langfuse public REST API and emits flat CSVs.

trace_id derivation: PDCA stores Langfuse traces with id = md5(run_id) when
run_id is not a 32-hex UUID (see pdca/observability/langfuse_client.py:94).
We replicate that here so the run_ids file from run_d1_sessions.py is enough.

Outputs (in --output-dir):
  - traces.csv          — one row per run_id (id, name, start, end, totalCost, ...)
  - node_latency.csv    — observation rows whose name starts with "node:"
  - llm_calls.csv       — generation observations (model, latency, prompt/output tokens)
  - hitl_timing.csv     — observations named "hitl:wait" with decision + latency_human_ms
  - sub_spans.csv       — other manual spans (rag:*, risk.pass1, risk.pass2_rag, ...)
  - scores.csv          — score events emitted via emit_score(...)

Usage:
    python scripts/langfuse_export.py \
        --run-ids-file benchmarks/results/d1_20260505/run_ids.txt \
        --output-dir   benchmarks/results/d1_20260505/
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

LF_HOST = (os.getenv("LANGFUSE_HOST") or "").rstrip("/")
LF_PK = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LF_SK = os.getenv("LANGFUSE_SECRET_KEY", "")

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def log(msg: str, level: str = "INFO") -> None:
    prefix = {"INFO": "[+]", "WARN": "[!]", "ERROR": "[x]", "OK": "[v]"}
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{ts} {prefix.get(level, '[ ]')} {msg}", flush=True)


def trace_id_for(run_id: str) -> str:
    """Mirror pdca.observability.langfuse_client.langfuse_trace_id."""
    candidate = (run_id or "").replace("-", "").lower()
    if _HEX32.match(candidate):
        return candidate
    return hashlib.md5((run_id or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Langfuse REST client (public API)
# ---------------------------------------------------------------------------
class LangfuseClient:
    def __init__(self, host: str, pk: str, sk: str, timeout: float = 15.0):
        if not host:
            raise ValueError("LANGFUSE_HOST is empty -- check .env")
        if not (pk and sk):
            raise ValueError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY missing")
        self.base = host.rstrip("/")
        self.client = httpx.Client(auth=(pk, sk), timeout=timeout)

    def close(self):
        self.client.close()

    def get_trace(self, trace_id: str) -> dict | None:
        r = self.client.get(f"{self.base}/api/public/traces/{trace_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def list_observations(self, trace_id: str) -> list[dict]:
        """Paginate /api/public/observations?traceId=..."""
        out: list[dict] = []
        page = 1
        while True:
            r = self.client.get(
                f"{self.base}/api/public/observations",
                params={"traceId": trace_id, "page": page, "limit": 100},
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("data") or []
            out.extend(items)
            meta = data.get("meta") or {}
            total_pages = int(meta.get("totalPages") or 1)
            if page >= total_pages or not items:
                break
            page += 1
        return out

    def list_scores(self, trace_id: str) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            r = self.client.get(
                f"{self.base}/api/public/scores",
                params={"traceId": trace_id, "page": page, "limit": 100},
            )
            if r.status_code == 404:
                return out
            r.raise_for_status()
            data = r.json()
            items = data.get("data") or []
            out.extend(items)
            meta = data.get("meta") or {}
            total_pages = int(meta.get("totalPages") or 1)
            if page >= total_pages or not items:
                break
            page += 1
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_iso(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _ms_between(start: Any, end: Any) -> float | None:
    if not (start and end):
        return None
    try:
        s = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        e = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return round((e - s).total_seconds() * 1000.0, 3)
    except Exception:
        return None


def _safe_json(v: Any) -> str:
    if v is None:
        return ""
    try:
        return json.dumps(v, ensure_ascii=False, default=str)[:2000]
    except Exception:
        return str(v)[:2000]


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------
TRACE_FIELDS = ["run_id", "trace_id", "name", "createdAt", "startedAt", "endedAt",
                "duration_ms", "totalCost", "tags", "metadata_keys"]
NODE_FIELDS = ["run_id", "trace_id", "node_name", "obs_id", "startTime", "endTime",
               "duration_ms", "level", "statusMessage", "metadata_keys"]
LLM_FIELDS = ["run_id", "trace_id", "obs_id", "name", "model", "startTime", "endTime",
              "duration_ms", "input_tokens", "output_tokens", "total_tokens",
              "input_cost", "output_cost", "total_cost"]
HITL_FIELDS = ["run_id", "trace_id", "obs_id", "name", "startTime", "endTime",
               "duration_ms", "decision", "latency_human_ms", "task_id"]
SUBSPAN_FIELDS = ["run_id", "trace_id", "obs_id", "name", "startTime", "endTime",
                  "duration_ms", "level", "metadata_keys"]
SCORE_FIELDS = ["run_id", "trace_id", "score_id", "name", "value", "comment", "timestamp"]


def build_trace_row(run_id: str, trace_id: str, t: dict) -> dict:
    md = t.get("metadata") or {}
    return {
        "run_id": run_id,
        "trace_id": trace_id,
        "name": t.get("name") or "",
        "createdAt": _to_iso(t.get("createdAt")),
        "startedAt": _to_iso(t.get("timestamp") or t.get("startTime")),
        "endedAt": _to_iso(t.get("endedAt") or t.get("endTime")),
        "duration_ms": _ms_between(
            t.get("timestamp") or t.get("startTime"),
            t.get("endedAt") or t.get("endTime"),
        ),
        "totalCost": t.get("totalCost"),
        "tags": _safe_json(t.get("tags")),
        "metadata_keys": ",".join(sorted((md or {}).keys())),
    }


def build_node_row(run_id: str, trace_id: str, o: dict) -> dict:
    name = o.get("name") or ""
    md = o.get("metadata") or {}
    start = o.get("startTime")
    end = o.get("endTime")
    return {
        "run_id": run_id, "trace_id": trace_id,
        "node_name": name[len("node:"):] if name.startswith("node:") else name,
        "obs_id": o.get("id"),
        "startTime": _to_iso(start), "endTime": _to_iso(end),
        "duration_ms": _ms_between(start, end),
        "level": o.get("level") or "",
        "statusMessage": (o.get("statusMessage") or "")[:200],
        "metadata_keys": ",".join(sorted((md or {}).keys())),
    }


def build_llm_row(run_id: str, trace_id: str, o: dict) -> dict:
    usage = o.get("usage") or {}
    return {
        "run_id": run_id, "trace_id": trace_id, "obs_id": o.get("id"),
        "name": o.get("name") or "",
        "model": o.get("model") or "",
        "startTime": _to_iso(o.get("startTime")), "endTime": _to_iso(o.get("endTime")),
        "duration_ms": _ms_between(o.get("startTime"), o.get("endTime")),
        "input_tokens": usage.get("input") or usage.get("promptTokens") or usage.get("inputTokens"),
        "output_tokens": usage.get("output") or usage.get("completionTokens") or usage.get("outputTokens"),
        "total_tokens": usage.get("total") or usage.get("totalTokens"),
        "input_cost": (o.get("calculatedInputCost") or (o.get("costDetails") or {}).get("input")),
        "output_cost": (o.get("calculatedOutputCost") or (o.get("costDetails") or {}).get("output")),
        "total_cost": (o.get("calculatedTotalCost") or o.get("totalCost") or (o.get("costDetails") or {}).get("total")),
    }


def build_hitl_row(run_id: str, trace_id: str, o: dict) -> dict:
    out = (o.get("output") or {}) if isinstance(o.get("output"), dict) else {}
    inp = (o.get("input") or {}) if isinstance(o.get("input"), dict) else {}
    return {
        "run_id": run_id, "trace_id": trace_id, "obs_id": o.get("id"),
        "name": o.get("name") or "",
        "startTime": _to_iso(o.get("startTime")), "endTime": _to_iso(o.get("endTime")),
        "duration_ms": _ms_between(o.get("startTime"), o.get("endTime")),
        "decision": out.get("decision") or inp.get("decision") or "",
        "latency_human_ms": out.get("latency_human_ms"),
        "task_id": inp.get("task_id") or out.get("task_id") or "",
    }


def build_subspan_row(run_id: str, trace_id: str, o: dict) -> dict:
    md = o.get("metadata") or {}
    return {
        "run_id": run_id, "trace_id": trace_id, "obs_id": o.get("id"),
        "name": o.get("name") or "",
        "startTime": _to_iso(o.get("startTime")), "endTime": _to_iso(o.get("endTime")),
        "duration_ms": _ms_between(o.get("startTime"), o.get("endTime")),
        "level": o.get("level") or "",
        "metadata_keys": ",".join(sorted((md or {}).keys())),
    }


def build_score_row(run_id: str, trace_id: str, s: dict) -> dict:
    return {
        "run_id": run_id, "trace_id": trace_id,
        "score_id": s.get("id"),
        "name": s.get("name") or "",
        "value": s.get("value"),
        "comment": (s.get("comment") or "")[:300],
        "timestamp": _to_iso(s.get("timestamp")),
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------
def write_csv(path: Path, fields: list[str], rows: Iterable[dict]) -> int:
    rows = list(rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    return len(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-ids-file", required=True, help="Plaintext file: 1 run_id per line")
    parser.add_argument("--output-dir", required=True, help="Where to write *.csv")
    parser.add_argument("--include-warmup", action="store_true",
                        help="(unused; warmup filtering happens at aggregation)")
    args = parser.parse_args()

    run_ids_path = Path(args.run_ids_file)
    if not run_ids_path.exists():
        log(f"--run-ids-file not found: {run_ids_path}", "ERROR")
        return 2
    run_ids = [r.strip() for r in run_ids_path.read_text(encoding="utf-8").splitlines() if r.strip()]
    if not run_ids:
        log("run_ids.txt is empty", "ERROR")
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"Langfuse host: {LF_HOST}")
    log(f"Run IDs to fetch: {len(run_ids)}")

    try:
        lf = LangfuseClient(LF_HOST, LF_PK, LF_SK)
    except Exception as e:
        log(f"Langfuse init failed: {e}", "ERROR")
        return 2

    traces, nodes, llms, hitls, subspans, scores = [], [], [], [], [], []
    failures: list[dict] = []

    for run_id in run_ids:
        tid = trace_id_for(run_id)
        log(f"  fetch run_id={run_id} trace_id={tid}")
        try:
            trace = lf.get_trace(tid)
        except Exception as e:
            log(f"    get_trace failed: {e}", "WARN")
            failures.append({"run_id": run_id, "trace_id": tid, "error": str(e)})
            continue
        if not trace:
            log(f"    trace not found (404)", "WARN")
            failures.append({"run_id": run_id, "trace_id": tid, "error": "404"})
            continue
        traces.append(build_trace_row(run_id, tid, trace))

        try:
            obs = lf.list_observations(tid)
        except Exception as e:
            log(f"    list_observations failed: {e}", "WARN")
            obs = []

        for o in obs:
            otype = (o.get("type") or "").upper()
            name = o.get("name") or ""
            if name.startswith("node:"):
                nodes.append(build_node_row(run_id, tid, o))
            elif otype == "GENERATION":
                llms.append(build_llm_row(run_id, tid, o))
            elif name.startswith("hitl:"):
                hitls.append(build_hitl_row(run_id, tid, o))
            elif otype == "SPAN":
                subspans.append(build_subspan_row(run_id, tid, o))

        try:
            score_list = lf.list_scores(tid)
        except Exception as e:
            log(f"    list_scores failed: {e}", "WARN")
            score_list = []
        for s in score_list:
            scores.append(build_score_row(run_id, tid, s))

    lf.close()

    # Write CSVs
    n_t = write_csv(out_dir / "traces.csv", TRACE_FIELDS, traces)
    n_n = write_csv(out_dir / "node_latency.csv", NODE_FIELDS, nodes)
    n_l = write_csv(out_dir / "llm_calls.csv", LLM_FIELDS, llms)
    n_h = write_csv(out_dir / "hitl_timing.csv", HITL_FIELDS, hitls)
    n_s = write_csv(out_dir / "sub_spans.csv", SUBSPAN_FIELDS, subspans)
    n_sc = write_csv(out_dir / "scores.csv", SCORE_FIELDS, scores)
    if failures:
        with open(out_dir / "fetch_failures.json", "w", encoding="utf-8") as f:
            json.dump(failures, f, indent=2)

    log("=" * 60)
    log(f"  traces        : {n_t}")
    log(f"  node_latency  : {n_n}")
    log(f"  llm_calls     : {n_l}")
    log(f"  hitl_timing   : {n_h}")
    log(f"  sub_spans     : {n_s}")
    log(f"  scores        : {n_sc}")
    if failures:
        log(f"  fetch_failures: {len(failures)} (see fetch_failures.json)", "WARN")
    log(f"Output: {out_dir}", "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
