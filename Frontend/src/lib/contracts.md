# Frontend ↔ Backend Contract

> Canonical surface between the React UI and the Python `pdca` services.
> The UI consumes a single domain object — `RunSession` — defined in
> `src/types/pdca.ts`. Any backend that wants to drive the UI must produce
> data shaped like `RunSession` (or be projected to it via `adapters.ts`).

## 1. Service base URLs

| Service     | Default                  | Env var               |
|-------------|--------------------------|-----------------------|
| Scanner API | `http://127.0.0.1:8000`  | `VITE_SCANNER_API_URL`|
| RAG API     | `http://localhost:8005`  | `VITE_RAG_API_URL`    |
| Chatbot API | (not yet implemented)    | `VITE_CHATBOT_API_URL`|

When `VITE_CHATBOT_API_URL` is unset, the FE runs in **mock mode** — every
`useRun()` call resolves the bundled `mockRun` so the UI is fully usable
without a backend.

## 2. Existing endpoints we already wire

### Scanner API (`pdca/api_server.py`)

| Method | Path                   | FE usage                                  |
|--------|------------------------|-------------------------------------------|
| POST   | `/v1/scan/group`       | submit a service-group scan (`s3`, ...)   |
| POST   | `/v1/scan/checks`      | submit specific Prowler check ids         |
| POST   | `/v1/scan/custom`      | submit a custom-checks JSON file          |
| GET    | `/v1/job/{job_id}`     | poll a single job                         |
| GET    | `/v1/jobs?limit&offset`| list recent jobs (used as health probe)   |

### Backend job shape → FE `ScanJob`

```jsonc
// GET /v1/job/{id}
{
  "job_id":          "job_abcd1234",
  "status":          "pending|running|completed|failed",
  "task_type":       "group|custom_file",
  "task_value":      "s3" | "iam_password_policy,...",
  "command_details": "scan group: s3",
  "submitted_time":  1714210000.123,   // unix seconds
  "start_time":      1714210001.456,
  "end_time":        1714210060.789,
  "duration_seconds": 59.3,
  "summary_text":    "ANSI-stripped Prowler stdout",
  "result":          [ /* OCSF findings list */ ],
  "error":           null
}
```

`adapters.jobToScanJob` projects this into `ScanJob`. `adapters.findingsFromJob`
walks `result[]` and emits `Finding` records.

## 3. RunSession — what's locked, what's stubbed

Source of truth: [`src/types/pdca.ts`](./../types/pdca.ts).

| Field                | Source today                          | Source after Sprint 2+        |
|----------------------|---------------------------------------|-------------------------------|
| `id`, `threadId`     | mock / `crypto.randomUUID()`          | `POST /v1/runs` response      |
| `status`             | derived from latest job status        | server-pushed via SSE         |
| `awsEnvironment`     | mock + values from Settings form      | `GET /v1/environment`         |
| `graphNodes`         | mock                                  | `GET /v1/runs/{id}`           |
| `scanJobs`           | **live** — adapted from `/v1/job/*`   | `GET /v1/runs/{id}`           |
| `findings`           | **live** — adapted from job result    | `GET /v1/runs/{id}`           |
| `toolCalls`          | mock                                  | `GET /v1/runs/{id}`           |
| `evidence`           | mock                                  | `GET /v1/runs/{id}`           |
| `remediationTasks`   | mock                                  | `GET /v1/runs/{id}`           |
| `executionLogs`      | mock                                  | `GET /v1/runs/{id}`           |
| `verifications`      | mock                                  | `GET /v1/runs/{id}`           |
| `messages`           | local UI state                        | local + server messages       |
| `report`             | mock                                  | `GET /v1/runs/{id}/report`    |

## 4. Future Chatbot API (Sprint 2+) — planned shape

This is the contract a future `pdca/api/chatbot.py` MUST implement. The
adapter layer is structured so wiring it requires touching ONLY
`adapters.ts` + `api.ts` — no view code changes.

```
GET  /v1/environment                          → AwsEnvironment
POST /v1/runs              {prompt, scope}    → { run_id }
GET  /v1/runs                                 → RunHistoryRow[]
GET  /v1/runs/{id}                            → RunSession
GET  /v1/runs/{id}/stream                     → SSE: { type, payload }
POST /v1/runs/{id}/messages    {text}         → { message_id }
POST /v1/runs/{id}/approvals/{task_id}
                          {decision}          → { ok }
GET  /v1/runs/{id}/report                     → DOCX (binary)
```

## 5. Failure mode

Every API call goes through `api.ts::request()` which:

1. Tries the network call.
2. On 4xx → throws `ApiError` (UI shows toast).
3. On 5xx / network error → returns `{ ok: false }` and the caller decides
   whether to fall back to mock.

`useRun()` always yields a non-null `RunSession` — never `undefined` — so
views render identically whether a backend exists or not.
