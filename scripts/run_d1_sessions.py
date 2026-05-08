"""D1 — End-to-end PDCA session runner for benchmark mean+/-std.

Workflow per session:
  1. degrade_s3_for_e2e.py --degrade   (re-break the test bucket)
  2. POST /v1/runs                      (start PDCA on chatbot API)
  3. Poll GET /v1/runs/{run_id} every 2s
       - on waiting_for_approval: auto-approve head pending task
       - end on completed | failed | timeout
  4. degrade_s3_for_e2e.py --revert    (restore snapshot)
  5. Append summary row to summary.csv + run_ids.txt

Env requirements (validated up-front):
  - Chatbot API on CHATBOT_API_URL (default http://127.0.0.1:9002)
  - Scanner API on SCANNER_API_URL (probed by chatbot for environment)
  - RAG API on RAG_API_URL (probed by chatbot for environment)
  - Ollama on OLLAMA_URL with the configured model
  - Langfuse self-host on LANGFUSE_HOST (optional but recommended)
  - AWS credentials with read+write to TEST_BUCKET

Usage:
    # Pre-flight only, no PDCA call
    python scripts/run_d1_sessions.py --bucket s3-test123-bucket --dry-run

    # Warm-up only (1 session, marked warmup=True in summary)
    python scripts/run_d1_sessions.py --bucket s3-test123-bucket --warmup-only

    # Production loop (5 sessions, no warmup flag)
    python scripts/run_d1_sessions.py --bucket s3-test123-bucket --n 5
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# UTF-8 stdout on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

CHATBOT_URL = os.getenv("CHATBOT_API_URL", "http://127.0.0.1:9002").rstrip("/")
SCANNER_URL = os.getenv("SCANNER_API_URL", "http://127.0.0.1:9001").rstrip("/")
RAG_URL = os.getenv("RAG_API_URL", "http://localhost:9005").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "").rstrip("/")

DEFAULT_PROMPT_TPL = (
    "Quet bao mat S3 cho bucket {bucket} va tu dong khac phuc cac finding rui ro cao."
)

TERMINAL_STATUSES = {"completed", "failed"}
APPROVAL_STATUS = "waiting_for_approval"


# ---------------------------------------------------------------------------
# Logging helpers (ASCII-safe)
# ---------------------------------------------------------------------------
def log(msg: str, level: str = "INFO") -> None:
    prefix = {"INFO": "[+]", "WARN": "[!]", "ERROR": "[x]", "OK": "[v]", "STEP": "[>]"}
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{ts} {prefix.get(level, '[ ]')} {msg}", flush=True)


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
def _http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(url)
            return 200 <= r.status_code < 500
    except Exception:
        return False


def preflight() -> dict:
    """Verify all upstream services are reachable. Return a status dict."""
    log("Pre-flight checks...", "STEP")
    # /v1/environment does AWS STS + RAG ping -> can take 5-10s on cold start.
    chatbot_ok = (
        _http_ok(f"{CHATBOT_URL}/docs", timeout=5.0)
        or _http_ok(f"{CHATBOT_URL}/v1/environment", timeout=15.0)
    )
    results = {
        "chatbot": chatbot_ok,
        "scanner": _http_ok(f"{SCANNER_URL}/health") or _http_ok(f"{SCANNER_URL}/"),
        "rag": _http_ok(f"{RAG_URL}/") or _http_ok(f"{RAG_URL}/health"),
        "ollama": _http_ok(f"{OLLAMA_URL}/api/tags"),
        "langfuse": (
            _http_ok(f"{LANGFUSE_HOST}/api/public/health") if LANGFUSE_HOST else False
        ),
    }
    for k, v in results.items():
        log(f"  {k:10s} {'OK' if v else 'DOWN'}", "OK" if v else "WARN")
    return results


# ---------------------------------------------------------------------------
# Subprocess wrappers for degrade/revert
# ---------------------------------------------------------------------------
def _run_degrade_script(bucket: str, mode: str) -> int:
    """mode in {'--degrade', '--revert'}. Returns exit code."""
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "degrade_s3_for_e2e.py"),
        "--bucket", bucket,
        mode,
    ]
    if mode == "--degrade":
        cmd.append("--yes")
    log(f"Subprocess: {' '.join(cmd[2:])}", "STEP")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        log(f"  exit={proc.returncode}", "ERROR")
        log(f"  stdout: {proc.stdout[-400:]}", "ERROR")
        log(f"  stderr: {proc.stderr[-400:]}", "ERROR")
    return proc.returncode


# ---------------------------------------------------------------------------
# Chatbot API client
# ---------------------------------------------------------------------------
def post_run(client: httpx.Client, prompt: str) -> dict:
    r = client.post(f"{CHATBOT_URL}/v1/runs", json={"prompt": prompt}, timeout=10.0)
    r.raise_for_status()
    return r.json()


def get_run(client: httpx.Client, run_id: str) -> dict:
    r = client.get(f"{CHATBOT_URL}/v1/runs/{run_id}", timeout=10.0)
    r.raise_for_status()
    return r.json()


def post_approval(client: httpx.Client, run_id: str, task_id: str, decision: str) -> dict:
    r = client.post(
        f"{CHATBOT_URL}/v1/runs/{run_id}/approvals/{task_id}",
        json={"decision": decision},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def find_pending_task_id(rs: dict) -> str | None:
    for t in (rs.get("remediationTasks") or []):
        if t.get("decision") == "pending":
            return t.get("id")
    return None


# ---------------------------------------------------------------------------
# Single-session driver
# ---------------------------------------------------------------------------
def run_session(
    client: httpx.Client,
    bucket: str,
    prompt: str,
    timeout_s: int,
    poll_interval_s: float,
    decision: str,
) -> dict:
    """Drive 1 PDCA run end-to-end. Return summary dict."""
    summary: dict = {
        "run_id": None,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "ended_at": None,
        "status": "unknown",
        "duration_s": None,
        "current_node_at_end": None,
        "num_findings": 0,
        "num_remediation_tasks": 0,
        "num_approvals_sent": 0,
        "approval_decision": decision,
        "approval_latencies_s": [],
        "error": None,
    }

    t0 = time.perf_counter()

    log("POST /v1/runs", "STEP")
    try:
        created = post_run(client, prompt)
    except Exception as e:
        summary["status"] = "start_failed"
        summary["error"] = f"{type(e).__name__}: {e}"
        log(f"start_run failed: {e}", "ERROR")
        return summary

    run_id = created.get("run_id")
    summary["run_id"] = run_id
    log(f"run_id = {run_id}", "OK")

    deadline = time.perf_counter() + timeout_s
    last_status = None
    waiting_t0: float | None = None
    approvals_sent: set[str] = set()

    while time.perf_counter() < deadline:
        try:
            rs = get_run(client, run_id)
        except Exception as e:
            log(f"poll get_run failed (transient): {e}", "WARN")
            time.sleep(poll_interval_s)
            continue

        status = rs.get("status") or "unknown"
        cur = rs.get("currentNode") or ""
        if status != last_status:
            log(f"status: {last_status} -> {status} (node={cur})", "INFO")
            last_status = status

        # Snapshot quick counts
        summary["num_findings"] = len(rs.get("findings") or [])
        summary["num_remediation_tasks"] = len(rs.get("remediationTasks") or [])

        if status == APPROVAL_STATUS:
            if waiting_t0 is None:
                waiting_t0 = time.perf_counter()
            tid = find_pending_task_id(rs)
            if tid and tid not in approvals_sent:
                latency = time.perf_counter() - waiting_t0
                summary["approval_latencies_s"].append(round(latency, 3))
                log(f"auto-approve task {tid} (decision={decision}, wait={latency:.2f}s)", "STEP")
                try:
                    post_approval(client, run_id, tid, decision)
                    approvals_sent.add(tid)
                    summary["num_approvals_sent"] += 1
                    waiting_t0 = None  # reset for next interrupt
                except Exception as e:
                    log(f"approval POST failed: {e}", "ERROR")
                    summary["error"] = f"approval_failed: {e}"
                    break

        if status in TERMINAL_STATUSES:
            summary["status"] = status
            summary["current_node_at_end"] = cur
            break

        time.sleep(poll_interval_s)
    else:
        summary["status"] = "timeout"
        summary["error"] = f"exceeded {timeout_s}s"
        log(f"TIMEOUT after {timeout_s}s", "ERROR")

    summary["ended_at"] = datetime.utcnow().isoformat() + "Z"
    summary["duration_s"] = round(time.perf_counter() - t0, 3)
    log(f"session done: status={summary['status']} duration={summary['duration_s']}s", "OK")
    return summary


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------
SUMMARY_FIELDS = [
    "session_index", "warmup", "run_id", "started_at", "ended_at", "status",
    "duration_s", "current_node_at_end", "num_findings",
    "num_remediation_tasks", "num_approvals_sent", "approval_decision",
    "approval_latencies_s", "error",
]


def append_summary(out_dir: Path, row: dict) -> None:
    path = out_dir / "summary.csv"
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in row.items()})


def append_run_id(out_dir: Path, run_id: str | None) -> None:
    if not run_id:
        return
    with open(out_dir / "run_ids.txt", "a", encoding="utf-8") as f:
        f.write(run_id + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True, help="S3 test bucket (must own; will be degraded+reverted)")
    parser.add_argument("--n", type=int, default=5, help="Number of sessions (default 5)")
    parser.add_argument("--warmup-only", action="store_true", help="Run 1 session marked warmup=True, then stop")
    parser.add_argument("--prompt", default=None, help="Override user prompt (default: standard S3 prompt)")
    parser.add_argument("--decision", default="approved", choices=["approved", "rejected", "skipped"],
                        help="Auto-decision at HITL review_task (default: approved)")
    parser.add_argument("--timeout", type=int, default=600, help="Per-session timeout sec (default 600)")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval sec (default 2.0)")
    parser.add_argument("--output-dir", default=None,
                        help="Output dir (default benchmarks/results/d1_<UTC-date>)")
    parser.add_argument("--skip-degrade", action="store_true", help="Skip degrade/revert (for debugging only)")
    parser.add_argument("--dry-run", action="store_true", help="Pre-flight + print plan, no PDCA / degrade calls")
    args = parser.parse_args()

    prompt = args.prompt or DEFAULT_PROMPT_TPL.format(bucket=args.bucket)
    n_sessions = 1 if args.warmup_only else args.n

    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        date = datetime.utcnow().strftime("%Y%m%d")
        out_dir = ROOT / "benchmarks" / "results" / f"d1_{date}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log(f"D1 session runner")
    log(f"  bucket          = {args.bucket}")
    log(f"  N sessions      = {n_sessions} {'(warmup-only)' if args.warmup_only else ''}")
    log(f"  prompt          = {prompt!r}")
    log(f"  decision        = {args.decision}")
    log(f"  timeout/session = {args.timeout}s")
    log(f"  output_dir      = {out_dir}")
    log(f"  skip_degrade    = {args.skip_degrade}")
    log(f"  dry_run         = {args.dry_run}")
    log("=" * 70)

    health = preflight()
    must_have = ["chatbot", "ollama"]
    missing = [k for k in must_have if not health[k]]
    if missing:
        log(f"Missing services (cannot proceed): {missing}", "ERROR")
        return 2
    if not health["langfuse"]:
        log("Langfuse DOWN -- traces will NOT be exported. Continue? (--dry-run skips this gate)", "WARN")
    if not health["rag"]:
        log("RAG DOWN -- rag_enrich node will soft-fail.", "WARN")
    if not health["scanner"]:
        log("Scanner DOWN -- scan_submit will fail. Aborting.", "ERROR")
        return 2

    if args.dry_run:
        log("DRY-RUN: not invoking degrade or PDCA. Exiting.", "OK")
        return 0

    # Persist run config alongside results for audit
    config_path = out_dir / "run_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({
            "bucket": args.bucket,
            "n_sessions": n_sessions,
            "warmup_only": args.warmup_only,
            "prompt": prompt,
            "decision": args.decision,
            "timeout_s": args.timeout,
            "poll_interval_s": args.poll_interval,
            "skip_degrade": args.skip_degrade,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "preflight": health,
            "endpoints": {
                "chatbot": CHATBOT_URL, "scanner": SCANNER_URL, "rag": RAG_URL,
                "ollama": OLLAMA_URL, "langfuse": LANGFUSE_HOST,
            },
            "ollama_model": OLLAMA_MODEL,
        }, f, indent=2)

    overall_t0 = time.perf_counter()
    with httpx.Client() as client:
        for i in range(1, n_sessions + 1):
            log("")
            log(f"========== Session {i}/{n_sessions} {'(WARMUP)' if args.warmup_only else ''} ==========")

            if not args.skip_degrade:
                rc = _run_degrade_script(args.bucket, "--degrade")
                if rc != 0:
                    log(f"degrade failed (rc={rc}); skipping this session", "ERROR")
                    append_summary(out_dir, {
                        "session_index": i, "warmup": args.warmup_only, "run_id": None,
                        "started_at": datetime.utcnow().isoformat() + "Z", "ended_at": None,
                        "status": "degrade_failed", "duration_s": None,
                        "current_node_at_end": None, "num_findings": 0,
                        "num_remediation_tasks": 0, "num_approvals_sent": 0,
                        "approval_decision": args.decision, "approval_latencies_s": [],
                        "error": f"degrade rc={rc}",
                    })
                    continue

            summary = run_session(
                client, args.bucket, prompt,
                timeout_s=args.timeout,
                poll_interval_s=args.poll_interval,
                decision=args.decision,
            )
            summary["session_index"] = i
            summary["warmup"] = args.warmup_only
            append_summary(out_dir, summary)
            append_run_id(out_dir, summary["run_id"])

            if not args.skip_degrade:
                rc = _run_degrade_script(args.bucket, "--revert")
                if rc != 0:
                    log(f"REVERT FAILED (rc={rc}). Bucket may be left in degraded state!", "ERROR")
                    log(f"  Manually run: python scripts/degrade_s3_for_e2e.py --bucket {args.bucket} --revert", "ERROR")

    overall_dt = time.perf_counter() - overall_t0
    log("")
    log("=" * 70)
    log(f"D1 runner done. {n_sessions} session(s) in {overall_dt:.1f}s", "OK")
    log(f"  summary.csv -> {out_dir / 'summary.csv'}")
    log(f"  run_ids.txt -> {out_dir / 'run_ids.txt'}")
    log("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
