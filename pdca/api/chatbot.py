"""Chatbot orchestration API — Phase D-web.

LangGraph-driven web API. Endpoints:

- `GET  /v1/environment`                       — AWS connection + RAG ping (cached 30s).
- `POST /v1/runs`                              — start a new PDCA run (background daemon thread).
- `GET  /v1/runs`                              — list runs (orchestrator + scanner job DB).
- `GET  /v1/runs/{run_id}`                     — current `RunSession` snapshot.
- `POST /v1/runs/{run_id}/approvals/{task_id}` — record HITL decision + resume graph.
- `GET  /v1/runs/{run_id}/report`              — download markdown / JSON report.

Threading: each run is one daemon thread inside `pdca.api.graph_runtime`.
The chatbot module itself is stateless — all state lives in the LangGraph
`SqliteSaver` checkpointer (`data/checkpoints/pdca_state.db`).
"""

from __future__ import annotations

import os
import re
import sqlite3
import textwrap
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from pdca.agents.intent_classifier import ChatContext, IntentClassifier
from pdca.agents.qa_agent import QAAgent
from pdca.agents.shared.rag_client import RAGClient
from pdca.storage.chat_history import get_chat_store
from pdca.api.graph_runtime import (
    cancel_run,
    get_run_metadata,
    get_state_history,
    get_state_values,
    list_run_ids,
    resume_after_decision,
    start_run,
)
from pdca.api.state_adapter import to_run_session
from pdca.config import settings
from pdca.observability.logger import get_logger

load_dotenv()
logger = get_logger("pdca.api.chatbot")

# Reuse scanner job DB for History view (combined with orchestrator runs).
JOB_DB_PATH = "data/jobs/scanner_jobs.db"


# ---------------------------------------------------------------------------
# Request / response models — kept loose; FE owns the canonical shape.
# ---------------------------------------------------------------------------
class CreateRunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    scope: Optional[str] = None


class CreateRunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str = "idle"


class EnvironmentResponse(BaseModel):
    status: str
    accountMask: str
    region: str
    credentialType: str
    lastValidatedAt: str
    bucketsDiscovered: int
    ragAvailable: bool


class ApprovalRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected|skipped)$")


# Unified chat ----------------------------------------------------------------
class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    thread_id: Optional[str] = None  # Phase 2: server-side persisted
    run_id: Optional[str] = None
    # Optional client-side history (rarely needed once thread_id is in use).
    history: List[ChatTurn] = Field(default_factory=list)


class ChatMessageOut(BaseModel):
    type: str  # "qa_answer" | "suggest_action" | "run_started" | "text" | "error"
    # Free-form payload per type — FE knows the shape.
    payload: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    messages: List[ChatMessageOut]
    intent: Dict[str, Any]  # {classified, confidence, reason, ...}
    thread_id: str
    run_id: Optional[str] = None  # set when a new run was started
    # Follow-up prompts the FE can surface as quick-input chips.
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)


class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    last_role: str
    last_content: str
    last_run_id: Optional[str] = None
    message_count: int
    created_at: float
    updated_at: float


class ThreadListResponse(BaseModel):
    items: List[ThreadSummary]


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None


class CreateThreadResponse(BaseModel):
    thread_id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int = 0
    last_role: str = ""
    last_content: str = ""
    last_run_id: Optional[str] = None


class ThreadMessageOut(BaseModel):
    id: int
    role: str
    content: str
    message_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    intent_meta: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = None
    created_at: float


class ThreadMessagesResponse(BaseModel):
    thread_id: str
    messages: List[ThreadMessageOut]


# ---------------------------------------------------------------------------
# Group inference (lightweight rule — full NLU lives in PlanningAgent)
# ---------------------------------------------------------------------------
_KNOWN_GROUPS = {
    "s3", "iam", "ec2", "rds", "kms", "ecr", "vpc", "cloudtrail", "guardduty",
}


def infer_group(prompt: str, default: str = "s3") -> str:
    lower = (prompt or "").lower()
    for g in _KNOWN_GROUPS:
        if re.search(rf"\b{g}\b", lower):
            return g
    return default


# ---------------------------------------------------------------------------
# AWS environment probe (cached)
# ---------------------------------------------------------------------------
def _mask_account(account_id: Optional[str]) -> str:
    if not account_id:
        return "————"
    s = str(account_id)
    if len(s) < 6:
        return s
    return s[:4] + "•" * (len(s) - 6) + s[-2:]


def _probe_aws() -> Dict[str, Any]:
    region = settings.aws_default_region
    profile = settings.aws_profile
    try:
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            session = boto3.Session(region_name=region)
            credential_type = "Access key (env)"
        else:
            session = boto3.Session(profile_name=profile, region_name=region)
            credential_type = f"Profile: {profile}"
    except BotoCoreError as e:
        return {
            "status": "not_connected", "accountMask": "————", "region": region,
            "credentialType": "(unconfigured)", "bucketsDiscovered": 0,
            "error": str(e),
        }

    try:
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        account = identity.get("Account")
    except NoCredentialsError:
        return {
            "status": "not_connected", "accountMask": "————", "region": region,
            "credentialType": credential_type, "bucketsDiscovered": 0,
        }
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = "expired_session" if "Expired" in code else "error"
        return {
            "status": status, "accountMask": "————", "region": region,
            "credentialType": credential_type, "bucketsDiscovered": 0,
            "error": str(e),
        }

    buckets = 0
    try:
        s3 = session.client("s3")
        resp = s3.list_buckets()
        buckets = len(resp.get("Buckets", []))
    except ClientError as e:
        logger.warning("list_buckets failed during /v1/environment", extra={"error": str(e)})

    return {
        "status": "connected",
        "accountMask": _mask_account(account),
        "region": region,
        "credentialType": credential_type,
        "bucketsDiscovered": buckets,
    }


def _probe_rag() -> bool:
    try:
        with httpx.Client(timeout=2.5) as c:
            r = c.get(settings.rag_api_url.rstrip("/") + "/")
            return r.status_code == 200
    except Exception:
        return False


_ENV_CACHE: Dict[str, Any] = {"value": None, "ts": 0.0}
_ENV_TTL_S = 30.0


def _cached_environment() -> EnvironmentResponse:
    now = time.time()
    if _ENV_CACHE["value"] is not None and now - _ENV_CACHE["ts"] < _ENV_TTL_S:
        return _ENV_CACHE["value"]
    aws = _probe_aws()
    rag_up = _probe_rag()
    resp = EnvironmentResponse(
        status=aws["status"],
        accountMask=aws["accountMask"],
        region=aws["region"],
        credentialType=aws["credentialType"],
        lastValidatedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        bucketsDiscovered=aws.get("bucketsDiscovered", 0),
        ragAvailable=rag_up,
    )
    _ENV_CACHE["value"] = resp
    _ENV_CACHE["ts"] = now
    return resp


# ---------------------------------------------------------------------------
# Unified chat — IntentClassifier + QAAgent singletons
# ---------------------------------------------------------------------------
_chat_agents: Dict[str, Any] = {"classifier": None, "qa": None, "rag_client": None}


def _get_chat_agents() -> Dict[str, Any]:
    if _chat_agents["classifier"] is None:
        rag = RAGClient(base_url=settings.rag_api_url, timeout=settings.rag_timeout_s)
        _chat_agents["rag_client"] = rag
        _chat_agents["classifier"] = IntentClassifier(
            model_name=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )
        _chat_agents["qa"] = QAAgent(
            model_name=settings.ollama_model,
            base_url=settings.ollama_base_url,
            rag_client=rag,
        )
        logger.info("chat agents ready", extra={
            "model": settings.ollama_model,
            "rag_url": settings.rag_api_url,
        })
    return _chat_agents


def _pending_clarification(run_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """If the referenced run halted on a clarification, return its payload.

    Shape: {"original_request": str, "question": str}. None otherwise.
    """
    if not run_id:
        return None
    snap = get_state_values(run_id)
    if not snap:
        return None
    values = snap.get("values") or {}
    plan = values.get("assessment_plan") or {}
    if plan.get("status") != "needs_clarification":
        return None
    return {
        "original_request": values.get("user_request", ""),
        "question": plan.get("clarification_question", ""),
    }


def _build_chat_context(req: ChatRequest, thread_id: str) -> ChatContext:
    current_service: Optional[str] = None
    findings_count = 0
    if req.run_id:
        snap = get_state_values(req.run_id)
        if snap:
            values = snap.get("values") or {}
            findings_count = len(values.get("normalized_findings") or [])
            groups = values.get("groups_to_scan") or []
            if groups:
                current_service = str(groups[0])

    # Prefer server-side history (authoritative). Fall back to client-provided
    # history only if no server messages exist yet for this thread.
    server_turns = get_chat_store().get_recent_for_context(thread_id, limit=4)
    if not server_turns and req.history:
        server_turns = [{"role": t.role, "content": t.content} for t in req.history[-4:]]
    return ChatContext(
        run_id=req.run_id,
        current_service=current_service,
        findings_count=findings_count,
        last_turns=server_turns,
    )


def _build_followup_suggestions(intent_kind: str, target_service: Optional[str], has_run: bool) -> List[Dict[str, Any]]:
    """Context-aware quick-input suggestions shown after each response.

    Returned as a list of `{label, kind, payload}` (kind = "qa" | "scan").
    FE renders them as chips above the input.
    """
    svc = target_service
    out: List[Dict[str, Any]] = []
    if intent_kind == "qa":
        if svc:
            out.append({"label": f"Quét {svc.upper()} ngay", "kind": "scan", "payload": f"scan {svc}"})
            out.append({"label": f"Best practices cho {svc.upper()}", "kind": "qa", "payload": f"What are best practices for {svc}?"})
        out.append({"label": "Tôi nên ưu tiên rủi ro nào?", "kind": "qa", "payload": "Which AWS security risks should I prioritize?"})
    elif intent_kind == "scan":
        out.append({"label": "Giải thích kết quả khi xong", "kind": "qa", "payload": "Explain the findings once the scan completes"})
        if svc:
            out.append({"label": f"Best practices cho {svc.upper()}", "kind": "qa", "payload": f"What are best practices for {svc}?"})
    else:  # mixed or fallback
        out.append({"label": "Xem báo cáo gần nhất", "kind": "qa", "payload": "Show last report summary"})
        if svc:
            out.append({"label": f"Quét {svc.upper()}", "kind": "scan", "payload": f"scan {svc}"})
    if has_run and intent_kind != "scan":
        out.append({"label": "Trạng thái run hiện tại?", "kind": "qa", "payload": "What is the status of the current run?"})
    return out[:4]


def _build_suggestion_chips(prompt: str, target_service: Optional[str]) -> Dict[str, Any]:
    """Same shape as Frontend SuggestActionCard."""
    svc = target_service
    if not svc:
        # try last-resort detection so chips still make sense
        from pdca.agents.intent_classifier import _detect_service as _ds
        svc = _ds(prompt)

    chips: List[Dict[str, Any]] = []
    if svc:
        chips = [
            {"label": f"Giải thích rủi ro {svc.upper()}", "icon": "qa",   "intent": "qa",   "payload": f"What are common {svc} risks?"},
            {"label": f"Quét {svc.upper()} trong account", "icon": "scan", "intent": "scan", "payload": f"scan {svc}"},
            {"label": f"Xem findings {svc.upper()} gần nhất", "icon": "evidence", "intent": "qa", "payload": f"Show recent {svc} findings"},
        ]
    else:
        chips = [
            {"label": "Giải thích AWS security basics", "icon": "qa",   "intent": "qa",   "payload": "What are AWS security best practices?"},
            {"label": "Quét S3 trong account",          "icon": "scan", "intent": "scan", "payload": "scan s3"},
            {"label": "Xem báo cáo gần nhất",           "icon": "report","intent": "qa",   "payload": "Show last report summary"},
        ]
    return {"prompt": "Bạn muốn tôi:", "chips": chips}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/v1", tags=["chatbot"])


@router.get("/ping")
def ping() -> Dict[str, str]:
    """Lightweight health probe — no AWS calls, responds in < 5 ms."""
    return {"ok": "true"}


@router.get("/environment", response_model=EnvironmentResponse)
def get_environment() -> EnvironmentResponse:
    return _cached_environment()


@router.post("/runs", response_model=CreateRunResponse)
def create_run(payload: CreateRunRequest) -> CreateRunResponse:
    group = infer_group(payload.prompt, default="s3")
    res = start_run(prompt=payload.prompt, scope=payload.scope, group=group)
    logger.info(
        "run started",
        extra={"run_id": res["run_id"], "thread_id": res["thread_id"], "scope": payload.scope, "group": group},
    )
    return CreateRunResponse(run_id=res["run_id"], thread_id=res["thread_id"])


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Unified chat: classify intent → route to QA / scan / mixed.

    Phase 2: thread_id-based history persistence. If `thread_id` is null,
    a new thread is created and returned in the response.
    """
    agents = _get_chat_agents()
    classifier: IntentClassifier = agents["classifier"]
    qa: QAAgent = agents["qa"]
    store = get_chat_store()

    is_new_thread = not req.thread_id
    thread_id = store.ensure_thread(
        req.thread_id,
        title=_thread_title_from_prompt(req.prompt) if is_new_thread else "",
    )

    # Persist user turn first so it appears in history even on error paths.
    store.append(thread_id, role="user", content=req.prompt, message_type="user_text", run_id=req.run_id)

    # ── CLARIFICATION FOLLOW-UP ─────────────────────────────────────────
    # If the referenced run halted on a clarifying question, treat this
    # message as the user's answer: merge it with the original request and
    # start a new run with `clarification_attempt=True` to suppress a second
    # ask. Skip intent classification — the user is answering a question.
    pending = _pending_clarification(req.run_id)
    if pending:
        merged = f"{pending['original_request']} — {req.prompt}".strip(" —")
        svc = infer_group(merged, default="s3")
        res = start_run(
            prompt=merged, scope=f"{svc} scan", group=svc,
            clarification_attempt=True,
        )
        new_run_id = res["run_id"]
        msg = ChatMessageOut(type="run_started", payload={
            "run_id": new_run_id,
            "thread_id": res["thread_id"],
            "service": svc,
            "text": (
                f"Đã ghi nhận. Khởi chạy run **{new_run_id}** với yêu cầu "
                f"đầy đủ: \"{merged}\"."
            ),
        })
        store.append(
            thread_id, role="assistant",
            content=msg.payload["text"], message_type=msg.type,
            payload=msg.payload, run_id=new_run_id,
        )
        return ChatResponse(
            messages=[msg],
            intent={"classified": "scan", "confidence": 1.0,
                    "reason": "clarification follow-up"},
            thread_id=thread_id,
            run_id=new_run_id,
            suggestions=[],
        )

    ctx = _build_chat_context(req, thread_id)
    intent = classifier.classify(req.prompt, ctx)
    intent_meta = intent.to_dict()
    logger.info("chat intent", extra={"thread_id": thread_id, "prompt_chars": len(req.prompt), **intent_meta})

    messages: List[ChatMessageOut] = []
    new_run_id: Optional[str] = None

    # ── SCAN ────────────────────────────────────────────────────────────
    if intent.intent == "scan":
        svc = intent.target_service or infer_group(req.prompt, default="s3")
        res = start_run(prompt=req.prompt, scope=f"{svc} scan", group=svc)
        new_run_id = res["run_id"]
        messages.append(ChatMessageOut(type="run_started", payload={
            "run_id": new_run_id,
            "thread_id": res["thread_id"],
            "service": svc,
            "text": (
                f"Run **{new_run_id}** đã khởi chạy. Agent sẽ quét **{svc}**, "
                "đánh giá rủi ro, đề xuất remediation và chờ duyệt."
            ),
        }))

    # ── QA ──────────────────────────────────────────────────────────────
    elif intent.intent == "qa":
        run_ctx = {
            "run_id": ctx.run_id,
            "service": ctx.current_service,
            "findings_count": ctx.findings_count,
        }
        ans = qa.answer(req.prompt, run_context=run_ctx, target_service=intent.target_service)
        messages.append(ChatMessageOut(type="qa_answer", payload={
            **ans.to_dict(),
            "intentMeta": {
                "classified": intent.intent,
                "confidence": round(intent.confidence, 3),
                "reason": intent.reason,
            },
        }))

    # ── MIXED ───────────────────────────────────────────────────────────
    else:
        run_ctx = {
            "run_id": ctx.run_id,
            "service": ctx.current_service,
            "findings_count": ctx.findings_count,
        }
        ans = qa.answer(req.prompt, run_context=run_ctx, target_service=intent.target_service)
        messages.append(ChatMessageOut(type="qa_answer", payload={
            **ans.to_dict(),
            "intentMeta": {
                "classified": intent.intent,
                "confidence": round(intent.confidence, 3),
                "reason": intent.reason,
            },
        }))
        messages.append(ChatMessageOut(
            type="suggest_action",
            payload=_build_suggestion_chips(req.prompt, intent.target_service),
        ))

    # Persist assistant turns. `content` is the human-readable string we can
    # surface in thread previews; full structured payload lives in payload_json.
    for m in messages:
        store.append(
            thread_id,
            role="assistant",
            content=_extract_preview(m),
            message_type=m.type,
            payload=m.payload,
            intent_meta=intent_meta,
            run_id=new_run_id or req.run_id,
        )

    suggestions = _build_followup_suggestions(
        intent_kind=intent.intent,
        target_service=intent.target_service,
        has_run=bool(new_run_id or req.run_id),
    )

    return ChatResponse(
        messages=messages,
        intent=intent_meta,
        thread_id=thread_id,
        run_id=new_run_id,
        suggestions=suggestions,
    )


# ---------------------------------------------------------------------------
# Thread management endpoints
# ---------------------------------------------------------------------------


@router.get("/threads", response_model=ThreadListResponse)
def list_threads(limit: int = 50, offset: int = 0) -> ThreadListResponse:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in [1, 200].")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0.")
    items = get_chat_store().list_threads(limit=limit, offset=offset)
    return ThreadListResponse(items=[ThreadSummary(**i.to_dict()) for i in items])


@router.post("/threads", response_model=CreateThreadResponse)
def create_thread(payload: CreateThreadRequest = CreateThreadRequest()) -> CreateThreadResponse:
    title = (payload.title or "New chat").strip()[:120] or "New chat"
    store = get_chat_store()
    thread_id = store.ensure_thread(title=title)
    # Return the exact row shape used by the sidebar so clients can insert it
    # without waiting for the next list refresh.
    with store._connect() as conn:  # type: ignore[attr-defined]
        row = conn.execute(
            "SELECT thread_id, title, created_at, updated_at FROM chat_threads WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
    return CreateThreadResponse(
        thread_id=thread_id,
        title=row["title"] if row else title,
        created_at=row["created_at"] if row else time.time(),
        updated_at=row["updated_at"] if row else time.time(),
    )


@router.get("/threads/{thread_id}/messages", response_model=ThreadMessagesResponse)
def get_thread_messages(thread_id: str, limit: int = 200) -> ThreadMessagesResponse:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be in [1, 1000].")
    rows = get_chat_store().get_history(thread_id, limit=limit, order="asc")
    if not rows:
        # 404 only when thread itself doesn't exist; empty thread returns [].
        threads = get_chat_store().list_threads(limit=1, offset=0)
        if not any(t.thread_id == thread_id for t in threads):
            # Cheap existence check via list is racy but acceptable; do a direct
            # query for accuracy.
            with get_chat_store()._connect() as conn:  # type: ignore[attr-defined]
                exists = conn.execute(
                    "SELECT 1 FROM chat_threads WHERE thread_id = ?",
                    (thread_id,),
                ).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="thread not found")
    return ThreadMessagesResponse(
        thread_id=thread_id,
        messages=[
            ThreadMessageOut(
                id=r.id, role=r.role, content=r.content,
                message_type=r.message_type,
                payload=_safe_payload(r.payload_json),
                intent_meta=_safe_payload(r.intent_meta_json) if r.intent_meta_json else None,
                run_id=r.run_id, created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str) -> Dict[str, Any]:
    ok = get_chat_store().delete_thread(thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"ok": True, "thread_id": thread_id}


# ---------------------------------------------------------------------------
# Helpers (thread management)
# ---------------------------------------------------------------------------


def _thread_title_from_prompt(prompt: str) -> str:
    p = (prompt or "").strip().replace("\n", " ")
    return p[:80] or "New chat"


def _extract_preview(m: ChatMessageOut) -> str:
    """Human-readable single-line summary stored in `content` for previews."""
    p = m.payload or {}
    if m.type in ("text", "run_started", "error"):
        return str(p.get("text") or "")[:500]
    if m.type == "qa_answer":
        md = str(p.get("markdown") or "")
        return md.replace("\n", " ").strip()[:300]
    if m.type == "suggest_action":
        chips = p.get("chips") or []
        labels = [str(c.get("label", "")) for c in chips if isinstance(c, dict)]
        return "Suggestions: " + " · ".join(labels[:3])
    return f"({m.type})"


def _safe_payload(s: Optional[str]) -> Dict[str, Any]:
    import json as _json
    if not s:
        return {}
    try:
        v = _json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE-streaming variant of /v1/chat.

    Event types (SSE `event:` field):
      - `meta`        — {thread_id, intent, run_id?}
      - `sources`     — [QASource]   (QA only, before deltas)
      - `delta`       — {"text": "..."}  (QA only, incremental markdown)
      - `messages`    — final ChatMessageOut[] (all intents)
      - `suggestions` — [{label, kind, payload}]
      - `done`        — {}
      - `error`       — {"message": "..."}

    For scan/mixed (non-streamable), we emit `meta` + `messages` + `suggestions`
    + `done` in one shot so the client logic stays uniform.
    """
    return StreamingResponse(_chat_stream_generator(req), media_type="text/event-stream")


def _sse(event: str, data: Any) -> bytes:
    import json as _json
    payload = _json.dumps(data, ensure_ascii=False, default=lambda o: getattr(o, "to_dict", lambda: str(o))())
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _chat_stream_generator(req: ChatRequest):
    """Generator producing SSE bytes. Persistence + intent routing identical
    to /v1/chat. QA path streams LLM tokens; scan/mixed yield final payload."""
    agents = _get_chat_agents()
    classifier: IntentClassifier = agents["classifier"]
    qa: QAAgent = agents["qa"]
    store = get_chat_store()

    try:
        is_new_thread = not req.thread_id
        thread_id = store.ensure_thread(
            req.thread_id,
            title=_thread_title_from_prompt(req.prompt) if is_new_thread else "",
        )
        store.append(thread_id, role="user", content=req.prompt, message_type="user_text", run_id=req.run_id)

        ctx = _build_chat_context(req, thread_id)
        intent = classifier.classify(req.prompt, ctx)
        intent_meta = intent.to_dict()
        logger.info("chat stream intent", extra={"thread_id": thread_id, **intent_meta})

        new_run_id: Optional[str] = None

        # ── SCAN ────────────────────────────────────────────────────────
        if intent.intent == "scan":
            svc = intent.target_service or infer_group(req.prompt, default="s3")
            res = start_run(prompt=req.prompt, scope=f"{svc} scan", group=svc)
            new_run_id = res["run_id"]
            yield _sse("meta", {"thread_id": thread_id, "intent": intent_meta, "run_id": new_run_id})
            messages = [{
                "type": "run_started",
                "payload": {
                    "run_id": new_run_id, "thread_id": res["thread_id"], "service": svc,
                    "text": f"Run **{new_run_id}** đã khởi chạy. Agent sẽ quét **{svc}**, đánh giá rủi ro, đề xuất remediation và chờ duyệt.",
                },
            }]
            store.append(thread_id, role="assistant",
                         content=messages[0]["payload"]["text"], message_type="run_started",
                         payload=messages[0]["payload"], intent_meta=intent_meta, run_id=new_run_id)
            yield _sse("messages", messages)

        # ── QA / MIXED ──────────────────────────────────────────────────
        else:
            yield _sse("meta", {"thread_id": thread_id, "intent": intent_meta})
            run_ctx = {
                "run_id": ctx.run_id, "service": ctx.current_service,
                "findings_count": ctx.findings_count,
            }
            # Stream QA answer.
            buffer: List[str] = []
            sources_payload: List[Dict[str, Any]] = []
            final_answer = None
            for event, data in qa.answer_stream(req.prompt, run_context=run_ctx, target_service=intent.target_service):
                if event == "sources":
                    sources_payload = [s.to_dict() for s in data]
                    yield _sse("sources", sources_payload)
                elif event == "delta":
                    buffer.append(data)
                    yield _sse("delta", {"text": data})
                elif event == "final":
                    final_answer = data
                elif event == "error":
                    yield _sse("error", {"message": str(data)})

            if final_answer is None:
                final_answer = type("X", (), {"to_dict": lambda self=None: {"markdown": "".join(buffer), "sources": sources_payload, "confidence": "low"}})()

            qa_msg = {
                "type": "qa_answer",
                "payload": {**final_answer.to_dict(), "intentMeta": {
                    "classified": intent.intent,
                    "confidence": round(intent.confidence, 3),
                    "reason": intent.reason,
                }},
            }
            messages = [qa_msg]

            if intent.intent == "mixed":
                chips = _build_suggestion_chips(req.prompt, intent.target_service)
                messages.append({"type": "suggest_action", "payload": chips})

            # Persist assistant turns to DB.
            for m in messages:
                preview = m["payload"].get("markdown") if m["type"] == "qa_answer" else (
                    "Suggestions: " + " · ".join(c.get("label", "") for c in m["payload"].get("chips", [])[:3])
                )
                store.append(thread_id, role="assistant",
                             content=(preview or "")[:300], message_type=m["type"],
                             payload=m["payload"], intent_meta=intent_meta, run_id=req.run_id)

            yield _sse("messages", messages)

        suggestions = _build_followup_suggestions(
            intent_kind=intent.intent,
            target_service=intent.target_service,
            has_run=bool(new_run_id or req.run_id),
        )
        yield _sse("suggestions", suggestions)
        yield _sse("done", {})
    except Exception as e:
        logger.error("chat stream failed", extra={"error": str(e)})
        yield _sse("error", {"message": str(e)})
        yield _sse("done", {})


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    snapshot = get_state_values(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Không tìm thấy run.")
    history = get_state_history(run_id, limit=200)

    # Overlay accountMask + lastValidatedAt from the env probe cache so the
    # FE Settings panel shows fresh data even before the run reaches
    # `environment_node`.
    env_extras: Dict[str, Any] = {}
    cached_env = _ENV_CACHE.get("value")
    if cached_env is not None:
        env_extras = {
            "accountMask": cached_env.accountMask,
            "credentialType": cached_env.credentialType,
            "lastValidatedAt": cached_env.lastValidatedAt,
        }
    return to_run_session(run_id, snapshot, history, aws_environment_extras=env_extras)


@router.post("/runs/{run_id}/approvals/{task_id}")
def post_approval(run_id: str, task_id: str, payload: ApprovalRequest) -> Dict[str, Any]:
    snapshot = get_state_values(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="run not found")
    ok = resume_after_decision(run_id, task_id, payload.decision)
    if not ok:
        raise HTTPException(status_code=409, detail="run not waiting for approval or task unknown")
    return {"ok": True, "decision": payload.decision}


@router.post("/runs/{run_id}/cancel")
def post_cancel_run(run_id: str) -> Dict[str, Any]:
    snapshot = get_state_values(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="run not found")
    ok = cancel_run(run_id)
    if not ok:
        raise HTTPException(status_code=409, detail="run could not be cancelled")
    return {"ok": True, "run_id": run_id, "status": "cancelled"}


@router.get("/runs/{run_id}/report")
def get_report(run_id: str, format: str = "pdf", download: bool = False) -> Any:
    """Return the run's report.

    format=pdf (default) streams the PDF for browser preview, download=1
    forces attachment; format=markdown keeps the legacy .md export; format=json
    returns structured sections.
    """
    snapshot = get_state_values(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="run not found")
    values = snapshot.get("values") or {}
    final_report = values.get("final_report")
    # ReportAgent.run() returns {"markdown": path, "html": ..., "pdf": ..., "validation_report": ...}
    # Older code paths may store a bare path string — handle both.
    if format == "json":
        # Reuse adapter — it produces the same `sections[]` shape.
        rs = to_run_session(run_id, snapshot, get_state_history(run_id, limit=10))
        return rs.get("report") or {}

    if format not in {"pdf", "markdown"}:
        raise HTTPException(status_code=400, detail="format must be pdf, markdown, or json")

    if isinstance(final_report, dict):
        report_path = final_report.get(format)
        if format == "pdf":
            html_path = final_report.get("html")
            if isinstance(html_path, str) and os.path.exists(html_path):
                inferred = os.path.join(os.path.dirname(html_path), "final_report.pdf")
                report_path = _html_to_pdf(html_path, inferred) or report_path
        if format == "pdf" and not report_path:
            markdown_path = final_report.get("markdown")
            if isinstance(markdown_path, str):
                inferred = os.path.join(os.path.dirname(markdown_path), "final_report.pdf")
                if os.path.exists(inferred):
                    report_path = inferred
                elif os.path.exists(markdown_path):
                    report_path = _markdown_to_pdf(markdown_path, inferred)
    else:
        report_path = final_report
        if format == "pdf" and isinstance(report_path, str):
            inferred = os.path.splitext(report_path)[0] + ".pdf"
            if os.path.exists(inferred):
                report_path = inferred
            elif os.path.exists(report_path):
                report_path = _markdown_to_pdf(report_path, inferred)

    if not report_path or not isinstance(report_path, str) or not os.path.exists(report_path):
        raise HTTPException(status_code=409, detail=f"{format} report not ready")

    if format == "pdf":
        disposition = "attachment" if download else "inline"
        filename = f"pdca-report-{run_id}.pdf"
        return FileResponse(
            report_path,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"could not read report: {e}")

    return PlainTextResponse(
        content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=pdca-report-{run_id}.md"},
    )


def _markdown_to_pdf(markdown_path: str, pdf_path: str) -> Optional[str]:
    try:
        from pdca.agents.report_module.exporters import _write_plain_pdf

        with open(markdown_path, "r", encoding="utf-8") as f:
            md = f.read()
        lines: List[str] = []
        for raw in md.splitlines():
            if not raw.strip():
                lines.append("")
            else:
                lines.extend(textwrap.wrap(raw.strip(), width=96) or [""])
        _write_plain_pdf(lines or ["Report generated with no text content."], pdf_path)
        return pdf_path if os.path.exists(pdf_path) else None
    except Exception as e:
        logger.warning("markdown to PDF fallback failed", extra={"path": markdown_path, "error": str(e)})
        return None


def _html_to_pdf(html_path: str, pdf_path: str) -> Optional[str]:
    try:
        edge_result = _html_to_pdf_browser(html_path, pdf_path)
        if edge_result:
            return edge_result

        from pdca.agents.report_module.exporters import export_pdf

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        result = export_pdf(html, pdf_path)
        return result if result and os.path.exists(result) else None
    except Exception as e:
        logger.warning("HTML to PDF export failed", extra={"path": html_path, "error": str(e)})
        return None


def _html_to_pdf_browser(html_path: str, pdf_path: str) -> Optional[str]:
    """Render the rich HTML report with a local Chromium browser when present.

    This preserves the same layout/charts users see in the HTML artifact. It is
    intentionally best-effort; if Edge/Chrome is unavailable we fall back to the
    Python exporters.
    """
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    candidates = [
        os.getenv("PDCA_CHROMIUM_PATH") or "",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("msedge") or "",
        shutil.which("chrome") or "",
        shutil.which("chromium") or "",
    ]
    browser = next((p for p in candidates if p and os.path.exists(p)), None)
    if not browser:
        return None

    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    file_url = Path(html_path).resolve().as_uri()
    with tempfile.TemporaryDirectory(prefix="pdca-chromium-") as user_data_dir:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-extensions",
            "--allow-file-access-from-files",
            f"--user-data-dir={user_data_dir}",
            f"--print-to-pdf={os.path.abspath(pdf_path)}",
            file_url,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=75)
    if proc.returncode == 0 and os.path.exists(pdf_path):
        return pdf_path
    logger.warning(
        "browser PDF export failed",
        extra={"path": html_path, "returncode": proc.returncode, "stderr": (proc.stderr or "")[-500:]},
    )
    return None


@router.get("/runs")
def list_runs(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit phải trong [1, 500].")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset phải >= 0.")

    items: List[Dict[str, Any]] = []

    # Active runs (orchestrator-driven).
    for rid in list_run_ids():
        snapshot = get_state_values(rid)
        if not snapshot:
            continue
        rs = to_run_session(rid, snapshot, [])  # skip history for list view
        meta = get_run_metadata(rid) or {}
        started_at = rs.get("startedAt") or _ts(meta.get("started_at", time.time()))
        items.append({
            "id": rs["id"],
            "target": meta.get("scope") or (meta.get("prompt") or "")[:80] or rs["currentNode"],
            "status": rs["status"],
            "startedAt": started_at,
            "durationMs": 0,
            "findingsTotal": len(rs.get("findings") or []),
            "remediated": sum(
                1 for v in rs.get("verifications") or [] if v.get("result") == "passed"
            ),
            "reportStatus": (rs.get("report") or {}).get("status", "pending"),
            "awsAccountMask": (rs.get("awsEnvironment") or {}).get("accountMask", "————"),
            "kind": "run",
        })

    # Legacy scanner-only jobs (combined for History view).
    if os.path.exists(JOB_DB_PATH):
        with sqlite3.connect(JOB_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            jrows = conn.execute(
                "SELECT job_id, status, command_details, submitted_at, ended_at, "
                "duration_s FROM jobs ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        for j in jrows:
            items.append({
                "id": j["job_id"],
                "target": j["command_details"],
                "status": j["status"],
                "startedAt": _ts(j["submitted_at"]),
                "durationMs": int((j["duration_s"] or 0) * 1000),
                "findingsTotal": 0,
                "remediated": 0,
                "reportStatus": "pending",
                "awsAccountMask": "————",
                "kind": "scan_job",
            })

    items.sort(key=lambda x: x["startedAt"], reverse=True)
    return {"items": items[offset:offset + limit], "limit": limit, "offset": offset}


def _ts(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch or 0)))


# ---------------------------------------------------------------------------
# App factory — runs standalone on port 9002 by default.
# ---------------------------------------------------------------------------
app = FastAPI(title="PDCA Chatbot API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def _warmup() -> None:
    """Eager-build the graph singleton + warm env probe so first POST /v1/runs
    isn't slow."""
    from pdca.api.graph_runtime import get_app
    get_app()
    _cached_environment()
    logger.info("Chatbot API ready (graph compiled, env probed)")


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Chatbot API on 127.0.0.1:9002")
    uvicorn.run("pdca.api.chatbot:app", host="127.0.0.1", port=9002, reload=True)
