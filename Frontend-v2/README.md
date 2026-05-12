# Frontend-v2 — CLI-style PDCA chatbot UI

A from-scratch rewrite of `Frontend/` focused on a **terminal-style chat UI**:
- Single page, no router, no tabs.
- Type natural language; the chatbot backend classifies (`qa` / `scan` / `mixed`) and routes.
- Scan runs stream as log events. HITL approvals appear inline with clickable buttons (and `a`/`r`/`s`/`d` shortcuts).
- QA answers stream into markdown bubbles with sources + intent reasoning toggle.

## Run

```
cd Frontend-v2
npm install
npm run dev          # http://localhost:5174
```

Make sure the chatbot API is up on `127.0.0.1:9002` (proxied as `/api/chatbot`). Adjust via the `⚙` settings in the header.

## Architecture

```
src/
  App.tsx                  # layout + reducer + 2 effects (chat stream, run poll)
  api.ts                   # ping, getEnvironment, getRun, approve, chatStream (SSE)
  reducer.ts               # UiState + Action
  types.ts                 # trimmed RunSession + LogLine model
  projectors/runToLines.ts # RunSession → LogLine[] diff (idempotent, in-place poll updates)
  components/
    Header, Prompt, LogLineView, Bubble, ApprovalBlock, ProgressBar, Settings
```

### Two data streams, one log

- **Chat stream** (`POST /v1/chat/stream`, SSE): `meta` → `delta…` / `messages` → `sources` → `done`. Drives the QA bubble.
- **Run polling** (`GET /v1/runs/{id}` every 3s, slows to 8s when waiting on approval): projected into event lines via `projectRun`. Stops on `completed`/`failed`.

Both streams append into a single chronological `lines: LogLine[]`. The polling projector keeps a `Set<string>` fingerprint so it never double-emits, and tracks a `pollLineByJob` map so the progress line updates in place.

### Reasoning toggles

Every event line can carry a `reasoning` string. QA bubbles surface the BE-classified `intent` + `confidence` + `reason` from the `meta` SSE event. Approval blocks expose `ragSteps`, `effort`, `rollback`, `toolParams`, IAM permission — all behind collapsed `<details>` so the log stays scannable.

## Notes

- Always starts a fresh thread on load (no history rehydration).
- No mock mode — if the chatbot is unreachable, the UI shows the connection error and stays interactive (so settings can be edited).
- No `react-router`, no Radix, no `lucide-react`, no shadcn — only `react-markdown` + `remark-gfm` for QA rendering.
