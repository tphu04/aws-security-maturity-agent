# PDCA Prowler Agent — Chatbot Frontend

React + Vite UI driving an end-to-end AWS security PDCA pipeline.
The UI talks to three backend services (Scanner, Chatbot orchestrator, RAG)
plus optional Ollama for LLM-enriched remediation reasoning.

```
                ┌──────────────────────────────────────────────┐
                │              Chatbot Frontend (5173)          │
                │  Workspace · Approvals · Results · Report ·   │
                │            History · Settings                 │
                └────────┬───────────┬────────────┬─────────────┘
                         │           │            │
                  POST /v1/runs   /v1/jobs    /v1/retrieve/*
                         │           │            │
              ┌──────────▼──┐  ┌─────▼──────┐  ┌──▼─────────┐
              │  Chatbot    │  │  Scanner   │  │   RAG       │
              │  API 8002   │──│  API 8001  │  │  API 8005   │
              │ orchestrator│  │  Prowler   │  │  Chroma+BM25│
              └─────┬───────┘  └────────────┘  └─────────────┘
                    │
              POST /api/generate
                    │
              ┌─────▼────────┐
              │  Ollama      │
              │  11434       │
              └──────────────┘
```

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | ≥ 18 | for Vite + React |
| Python | 3.13 | main backend interpreter |
| Python 3.12 | 3.12.x | **separate** venv for Prowler 5.x (Prowler does not support 3.13) |
| Ollama | latest | `ollama pull llama3.2:latest` |
| AWS credentials | — | configured via `aws configure` (profile = `default`) |

## One-time setup

### Frontend
```bash
cd Chatbot-Frontend
npm install
```

### Backend
```bash
cd ../aws-security-maturity-agent

# Main venv (Python 3.13)
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install httpx          # used by chatbot API

# Prowler venv (Python 3.12) — required because Prowler 5.x does not support 3.13
py -3.12 -m venv venv-prowler
venv-prowler\Scripts\python.exe -m pip install prowler
```

### Ollama model
```bash
ollama pull llama3.2:latest
```

---

## Run everything (4 terminals)

The backend has 3 services + Ollama. Use 4 separate terminals so each log
stays readable. All commands are PowerShell — adjust quoting for cmd/bash.

### Terminal 1 — Scanner API (port 8001)
```powershell
cd d:\DoAn\aws-security-maturity-agent
$env:PROWLER_PYTHON = "$PWD\venv-prowler\Scripts\python.exe"
venv\Scripts\python.exe -m uvicorn pdca.api_server:app --host 127.0.0.1 --port 8001
```

### Terminal 2 — RAG API (port 8005)
```powershell
cd d:\DoAn\aws-security-maturity-agent
venv\Scripts\python.exe RAG\start.py --port 8005
```
*First boot takes ~30s — sentence-transformers + chromadb load.*

### Terminal 3 — Chatbot orchestrator API (port 8002)
```powershell
cd d:\DoAn\aws-security-maturity-agent
$env:SCANNER_API_URL = "http://127.0.0.1:8001"
$env:OLLAMA_MODEL    = "llama3.2:latest"
$env:PDCA_LLM_ENRICH = "1"
venv\Scripts\python.exe -m uvicorn pdca.api.chatbot:app --host 127.0.0.1 --port 8002
```

### Terminal 4 — Frontend (port 5173)
```powershell
cd d:\DoAn\Chatbot-Frontend
npm run dev
```

Open <http://localhost:5173>.

---

## First-run checklist (in the UI)

1. **Settings** (top-right) — set the three URLs:
   - Scanner API: `http://127.0.0.1:8001`
   - RAG API: `http://localhost:8005`
   - Chatbot API: `http://127.0.0.1:8002`
2. **Save Endpoints** → **Test Connection** → all three badges green.
3. **Workspace** → type `scan s3` → Enter.

You should see the agent narrate every step:

```
🔐 Đang xác thực kết nối AWS …
[planning card]
[scan_submitted card: job_xxx]
⏳ Prowler đang quét …
[findings_collected: 5 FAIL · 21 PASS · 2 MANUAL]
📊 Đang phân tích rủi ro …
🤖 RemediationPlannerAgent đang chạy … gọi LLM (Ollama) …
✅ Đã lập 7 kế hoạch sửa lỗi. Vui lòng review từng task bên dưới.
[remediation_offer ×7  with Approve / Reject inline + LLM reasoning]
```

Approve / Reject each task → ExecutionAgent runs → Verification → Report.

---

## What lives where

| File | Purpose |
|------|---------|
| `src/lib/api.ts` | HTTP client for Scanner / RAG / Chatbot APIs. URL persistence in `localStorage`. |
| `src/lib/adapters.ts` | Pure functions that map backend payloads → FE `RunSession` types. |
| `src/lib/contracts.md` | Canonical FE↔BE contract documentation. |
| `src/state/run.tsx` | `RunProvider` — owns the live `RunSession`, polls `/v1/runs/{id}` every 3s, pushes approvals to backend. |
| `src/views/WorkspaceView.tsx` | Chat UI. Submits `scan s3` etc. via the chatbot orchestrator. |
| `src/views/ApprovalsView.tsx` | HITL approval queue. |
| `src/views/ResultsView.tsx` | Findings table + dashboard, derived from live `run.findings`. |
| `src/views/ReportView.tsx` | Markdown report preview + download. |
| `src/views/HistoryView.tsx` | Past runs from `/v1/runs`. |
| `src/components/evidence/ToolTracePanel.tsx` | Right-hand transparency panel: live node, tool calls grouped by node, evidence, graph timeline. |

## Backend endpoints used by the FE

| Method | URL | Purpose |
|--------|-----|---------|
| GET    | `:8001/v1/jobs?limit=1` | Scanner health probe |
| POST   | `:8001/v1/scan/group`   | Direct scan (fallback when chatbot offline) |
| GET    | `:8001/v1/job/{id}`     | Poll a Prowler job |
| GET    | `:8002/v1/environment`  | AWS account + RAG ping (cached 30s) |
| POST   | `:8002/v1/runs`         | Start a full PDCA run |
| GET    | `:8002/v1/runs`         | List runs (for History view) |
| GET    | `:8002/v1/runs/{id}`    | Full `RunSession` snapshot — polled every 3s |
| POST   | `:8002/v1/runs/{id}/approvals/{task_id}` | Approve / reject HITL tasks |
| GET    | `:8002/v1/runs/{id}/report?format=markdown` | Download the report |
| GET    | `:8005/`                | RAG health probe |

## Environment variables (FE)

Override the default URLs at build time via `.env.local`:

```env
VITE_SCANNER_API_URL=http://127.0.0.1:8001
VITE_RAG_API_URL=http://localhost:8005
VITE_CHATBOT_API_URL=http://127.0.0.1:8002
```

If unset, sensible defaults are baked into `src/lib/api.ts`. URLs are also
persisted to `localStorage` once the user clicks **Save Endpoints**.

## Mock mode

If the chatbot API is down, the FE silently falls back to:
- **Scanner-only path** — `scan s3` submits a Prowler job directly via
  `/v1/scan/group`. No HITL flow. No report generation.
- **Mock data** — the bundled `mockRun` keeps the UI usable (History view,
  Results view) for offline demos.

The FE is therefore always usable, even if only some services are up.

## Troubleshooting

### "Chatbot offline" badge stays red even after `uvicorn` reports running
- The first call to `/v1/environment` takes ~5s (boto3 STS + S3 list_buckets +
  RAG ping). The FE waits up to 12s. Subsequent calls are cached for 30s.
- If still red: open DevTools → Network → click **Test Connection** → look at
  the `/v1/environment` request. CORS errors mean the backend was not started
  with the right `--host` (must be `127.0.0.1` to match the URL).

### `Errno 10048 — only one usage of each socket address`
Windows leaves "ghost listeners" when a uvicorn process exits abnormally.
Kill them and try again:
```powershell
Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Prowler scan fails with `No module named prowler`
Scanner API was started with the wrong interpreter. Make sure
`PROWLER_PYTHON` points at the **Python 3.12 venv** before launching.

### Ollama `model 'gemma3:4b' not found`
Set `OLLAMA_MODEL` to whatever you have locally:
```powershell
ollama list
$env:OLLAMA_MODEL = "llama3.2:latest"   # or whatever
```

### Run stuck in `waiting_for_approval`
The orchestrator waits for **every** task to have a non-pending decision.
Open the Approvals view and click Approve / Reject on the remaining tasks,
or POST decisions manually:
```bash
curl -X POST http://127.0.0.1:8002/v1/runs/<run_id>/approvals/<task_id> \
  -H "Content-Type: application/json" -d '{"decision":"rejected"}'
```

## Build for production

```bash
npm run build
npm run preview        # serves dist/ on port 4173
```

The build is plain static assets — host on any CDN / S3 + CloudFront.
