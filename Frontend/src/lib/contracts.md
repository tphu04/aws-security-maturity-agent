# Frontend ↔ Backend Contract

> Canonical surface between the React UI and the Python `pdca` services.
> The UI consumes a single domain object — `RunSession` — defined in
> `src/types/pdca.ts`. Any backend that wants to drive the UI must produce
> data shaped like `RunSession` (or be projected to it via `adapters.ts`).

## 1. Service base URLs

| Service     | Default                  | Env var               |
|-------------|--------------------------|-----------------------|
| Scanner API | `http://127.0.0.1:9001`  | `VITE_SCANNER_API_URL`|
| Chatbot API | `http://127.0.0.1:9002`  | `VITE_CHATBOT_API_URL`|
| RAG API     | `http://localhost:9005`  | `VITE_RAG_API_URL`    |

When the chatbot URL is unreachable, the FE falls back to **scanner-only
mode** (no HITL, no report) so the UI remains usable for raw scans. When
all three are unreachable the FE renders the bundled `mockRun`.

## 2. Architecture (post Phase D-web)

```
Frontend ────────► Chatbot API (9002) ─────────► LangGraph runtime
  /v1/runs           pdca/api/chatbot.py            pdca/graph/graph.py
  /v1/runs/{id}      pdca/api/graph_runtime.py      build_graph(SqliteSaver)
  /approvals/...     pdca/api/state_adapter.py      interrupt_before=review_task
                          │
                          └──────► Scanner API (9001) ── Prowler subprocess
                          └──────► RAG API (9005)
                          └──────► Ollama (11434, optional)
```

The chatbot API is a **thin web driver** around a singleton compiled
LangGraph app. State lives in `data/checkpoints/pdca_state.db`
(`SqliteSaver`). HITL is implemented natively via LangGraph's
`interrupt_before=["review_task"]` — each `POST /approvals/{task_id}`
calls `app.update_state(...)` then resumes via `app.stream(None, config)`.

## 3. Endpoints

### Scanner API (`pdca/api_server.py`) — port 9001

| Method | Path                   | FE usage                                  |
|--------|------------------------|-------------------------------------------|
| POST   | `/v1/scan/group`       | Scanner-only fallback                     |
| POST   | `/v1/scan/checks`      | Scanner-only fallback                     |
| POST   | `/v1/scan/custom`      | Scanner-only fallback (custom checks)     |
| GET    | `/v1/job/{job_id}`     | Poll a single job (fallback path)         |
| GET    | `/v1/jobs?limit&offset`| List recent jobs (used as health probe)   |

In normal operation, the FE does **not** call these directly — the
chatbot orchestrator drives the scanner via internal LangGraph nodes.

### Chatbot API (`pdca/api/chatbot.py`) — port 9002

| Method | Path                                   | FE usage                                      |
|--------|----------------------------------------|-----------------------------------------------|
| GET    | `/v1/environment`                      | AWS connection + RAG ping (cached 30s)        |
| POST   | `/v1/runs`                             | Start a new PDCA run                          |
| GET    | `/v1/runs?limit&offset`                | History view: orchestrator runs + scan jobs   |
| GET    | `/v1/runs/{id}`                        | **Polled every 3s** — full `RunSession`       |
| POST   | `/v1/runs/{id}/approvals/{task_id}`    | HITL decision (decision: approved / rejected) |
| GET    | `/v1/runs/{id}/report?format=markdown` | Download report (markdown or json)            |

### RAG API — port 9005

The frontend only pings `GET /` for health. Multi-query RAG calls
(`/v1/retrieve/report_context`, `/v1/resolve/mapping`) happen
**server-side** inside the LangGraph `rag_enrich` node, never FE→RAG.

## 4. RunSession projection — what each field means

Source of truth: [`src/types/pdca.ts`](./../types/pdca.ts).

The `GET /v1/runs/{id}` response is built by
`pdca/api/state_adapter.py:to_run_session()` from the LangGraph
`PDCAState` snapshot + `app.get_state_history(config)`.

| Field                | Source PDCAState field                                                  |
|----------------------|-------------------------------------------------------------------------|
| `id`, `threadId`     | `state.run_id` (1:1 with LangGraph `thread_id`)                          |
| `status`             | derived from `snapshot.next` head node (e.g. `("review_task",)` → `waiting_for_approval`) |
| `currentNode`        | `snapshot.next[0]` if interrupted, else last completed node              |
| `awsEnvironment`     | `state.aws_context` + overlay from `_probe_aws()` cache                  |
| `findings`           | `state.prioritized_findings` (preferred) or `state.normalized_findings`  |
| `scanJobs`           | merge `state.pending_jobs ∪ state.completed_jobs`                        |
| `remediationTasks`   | `state.remediation_tasks` + `state.task_execution_plan` (decision/task)  |
| `executionLogs`      | `state.execution_logs`                                                    |
| `verifications`      | `state.verification_results` (= `AnalysisAgent.diff_result`)              |
| `report.sections`    | parse markdown file at `state.final_report` path                         |
| `graphNodes`         | walk `app.get_state_history(config)`, group writes by node               |
| `toolCalls`          | derive from `execution_logs` + `completed_jobs` (1 per tool invocation)  |
| `evidence`           | derive: 1 per FAIL finding + 1 per execution_log + 1 per verification    |
| `messages`           | **client-side only** — generated from status transitions                  |
| `ragBundle`          | `state.rag_bundle` (set by `rag_enrich_node`)                            |

Private fields (`_*` like `_langfuse_trace_id`) are stripped in the adapter.

## 5. HITL flow — per-task interrupt loop

```
T0: POST /v1/runs          → run_id, thread_id (background graph runs to interrupt)
T1: GET /v1/runs/{id}      → status="waiting_for_approval", currentNode="review_task",
                              remediationTasks[*].decision="pending"
T2: POST /approvals/task_1 {decision: approved}
                            → app.update_state({task_execution_plan: {task_1: approve},
                                                current_task_index: 1})
                            → app.stream(None, config)  // resumes 1 step → interrupts again
T3: GET /v1/runs/{id}      → still waiting, idx=1
T4: POST /approvals/task_2 → ...
T5: POST /approvals/task_3 (last) → graph reaches reset_index → execution → verification → report
T6: GET /v1/runs/{id}      → status="completed", report ready
```

The FE's Approvals view sends one POST per task — no `/approvals/batch`
endpoint exists. This matches LangGraph's intended HITL pattern.

## 6. Polling vs SSE

The FE polls `GET /v1/runs/{id}` every **3 seconds** (`state/run.tsx:256`).
SSE was considered (`/v1/runs/{id}/stream`) but is **not implemented** —
polling is sufficient for the demo and avoids async event-pump
complexity inside LangGraph nodes. Polling stops automatically when
`status` reaches `completed` or `failed`.

## 7. Failure mode

Every API call goes through `api.ts::request()`:

1. Tries the network call with a 10s timeout.
2. On 4xx → throws `ApiError` (UI shows toast).
3. On 5xx / network error → returns `{ ok: false }` and the caller
   decides whether to fall back.

`useRun()` always yields a non-null `RunSession` — never `undefined` —
so views render identically whether a backend exists or not. When the
chatbot is down, the FE silently degrades to the scanner-only path.

## 8. Mock mode (offline)

If `VITE_CHATBOT_API_URL` is unset **and** the scanner is unreachable,
the FE renders the bundled `mockRun` from `src/data/mockRun.ts` so the
UI is fully usable for offline demos. History view shows `mockHistory`.
