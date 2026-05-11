"""QAAgent — trả lời câu hỏi tổng quát về AWS security bằng RAG + LLM.

Phase 1 — Unified Chat. Khi IntentClassifier trả `qa` hoặc `mixed`, endpoint
`/v1/chat` gọi `QAAgent.answer()`.

Flow:
  1. RAG retrieve top-k Prowler checks bằng query free-form.
  2. Build prompt kèm context (snippet + check_id) — citation markers `[1]..[N]`.
  3. LLM (Ollama) sinh câu trả lời markdown, giữ citation markers.
  4. Return `QAAnswer` với `markdown` + `sources` để FE render.

Graceful degradation: RAG down → vẫn trả lời nhưng note "no sources retrieved".
LLM down → return fallback message thay vì raise.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Generator, List, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from pdca.agents.shared.rag_client import RAGClient
from pdca.observability.logger import get_logger
from pdca.observability.tracing import span as obs_span

logger = get_logger(__name__)


@dataclass
class QASource:
    check_id: Optional[str] = None
    title: str = ""
    url: Optional[str] = None
    snippet: Optional[str] = None
    score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        # FE expects camelCase `checkId`.
        return {
            "checkId": self.check_id,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "score": self.score,
        }


@dataclass
class QAAnswer:
    markdown: str
    sources: List[QASource] = field(default_factory=list)
    confidence: str = "medium"  # "high" | "medium" | "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "markdown": self.markdown,
            "sources": [s.to_dict() for s in self.sources],
            "confidence": self.confidence,
        }


ANSWER_PROMPT = """You are an AWS security expert helping a user understand a specific question.
Answer in the same language the user used (Vietnamese OR English). Be concise and concrete.

Use ONLY the retrieved sources below as factual grounding. When a fact comes from a source,
cite it inline with `[N]` matching the source index. Do NOT invent check IDs or AWS APIs that
are not in the sources. If the sources are insufficient, say so explicitly and suggest the
user run a scan.

Format rules:
- Use GitHub-flavored markdown (tables, code blocks with language tags, lists).
- Keep the answer under 250 words unless the user asked for deep detail.
- End with a one-line "Recommendation:" when relevant.

Retrieved sources:
{sources_block}

User question: "{question}"

{run_context_block}

Answer:"""


class QAAgent:
    def __init__(
        self,
        model_name: str,
        base_url: str = "http://localhost:11434",
        rag_client: Optional[RAGClient] = None,
        callbacks: Optional[List[BaseCallbackHandler]] = None,
        top_k: int = 5,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url
        self.rag_client = rag_client
        self.top_k = top_k
        self.callbacks: List[BaseCallbackHandler] = list(callbacks or [])
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0.2,
            callbacks=self.callbacks,
        )

    # ------------------------------------------------------------------
    def answer(
        self,
        question: str,
        run_context: Optional[Dict[str, Any]] = None,
        target_service: Optional[str] = None,
    ) -> QAAnswer:
        if not question or not question.strip():
            return QAAnswer(markdown="Xin lỗi, tôi chưa nhận được câu hỏi.", confidence="low")

        with obs_span(
            "agent:QAAgent",
            input={"question_chars": len(question), "target_service": target_service},
        ) as sp:
            sources = self._retrieve(question, target_service)
            try:
                markdown = self._generate(question, sources, run_context)
            except Exception as e:
                logger.error("QA LLM call failed", extra={"error": str(e)})
                markdown = self._fallback_markdown(question, sources, reason=str(e))

            answer = QAAnswer(
                markdown=markdown,
                sources=sources,
                confidence="high" if len(sources) >= 3 else "medium" if sources else "low",
            )
            sp.update(output={"sources_count": len(sources), "confidence": answer.confidence})
            return answer

    # ------------------------------------------------------------------
    def _retrieve(self, query: str, target_service: Optional[str]) -> List[QASource]:
        if not self.rag_client:
            logger.warning("QAAgent: no RAG client configured")
            return []
        try:
            result = self.rag_client.retrieve_checks(
                query=query,
                service=target_service,
                top_k=self.top_k,
                retrieval_mode="hybrid",
            )
        except Exception as e:
            logger.warning("RAG retrieve failed", extra={"error": str(e)})
            return []
        if not result:
            return []
        items = result.get("results") or []
        sources: List[QASource] = []
        for item in items[: self.top_k]:
            meta = item.get("metadata") or {}
            sources.append(
                QASource(
                    check_id=item.get("doc_id") or meta.get("check_id"),
                    title=str(meta.get("title") or item.get("doc_id") or "Untitled"),
                    url=meta.get("url"),
                    snippet=_truncate(meta.get("description") or item.get("snippet"), 200),
                    score=_safe_float(item.get("score")),
                )
            )
        return sources

    # ------------------------------------------------------------------
    def _generate(
        self,
        question: str,
        sources: List[QASource],
        run_context: Optional[Dict[str, Any]],
    ) -> str:
        sources_block = self._format_sources(sources)
        run_block = self._format_run_context(run_context)
        chain = ChatPromptTemplate.from_template(ANSWER_PROMPT) | self.llm | StrOutputParser()
        return chain.invoke({
            "question": question.strip(),
            "sources_block": sources_block,
            "run_context_block": run_block,
        }).strip()

    # ------------------------------------------------------------------
    def answer_stream(
        self,
        question: str,
        run_context: Optional[Dict[str, Any]] = None,
        target_service: Optional[str] = None,
    ) -> Generator[Tuple[str, Any], None, None]:
        """Yield (event, data) tuples for SSE streaming.

        Events:
            ("sources", List[QASource])         — emitted once before deltas
            ("delta",   str)                    — incremental markdown chunks
            ("final",   QAAnswer)               — full answer at end
            ("error",   str)                    — terminal error (no final)
        """
        if not question or not question.strip():
            yield ("final", QAAnswer(markdown="Xin lỗi, tôi chưa nhận được câu hỏi.", confidence="low"))
            return

        with obs_span(
            "agent:QAAgent.stream",
            input={"question_chars": len(question), "target_service": target_service},
        ) as sp:
            sources = self._retrieve(question, target_service)
            yield ("sources", sources)

            sources_block = self._format_sources(sources)
            run_block = self._format_run_context(run_context)
            chain = ChatPromptTemplate.from_template(ANSWER_PROMPT) | self.llm | StrOutputParser()

            buf: List[str] = []
            try:
                for chunk in chain.stream({
                    "question": question.strip(),
                    "sources_block": sources_block,
                    "run_context_block": run_block,
                }):
                    if not chunk:
                        continue
                    text = chunk if isinstance(chunk, str) else str(chunk)
                    buf.append(text)
                    yield ("delta", text)
            except Exception as e:
                logger.error("QA stream failed", extra={"error": str(e)})
                fallback = self._fallback_markdown(question, sources, reason=str(e))
                yield ("error", str(e))
                yield ("final", QAAnswer(
                    markdown=fallback, sources=sources,
                    confidence="low",
                ))
                return

            markdown = "".join(buf).strip()
            answer = QAAnswer(
                markdown=markdown,
                sources=sources,
                confidence="high" if len(sources) >= 3 else "medium" if sources else "low",
            )
            sp.update(output={"sources_count": len(sources), "chars": len(markdown), "confidence": answer.confidence})
            yield ("final", answer)

    # ------------------------------------------------------------------
    @staticmethod
    def _format_sources(sources: List[QASource]) -> str:
        if not sources:
            return "  (no sources retrieved — answer from general knowledge and say so)"
        lines = []
        for i, s in enumerate(sources, start=1):
            cid = s.check_id or "—"
            head = f"[{i}] check_id={cid} · title={s.title}"
            if s.snippet:
                head += f"\n     snippet: {s.snippet}"
            lines.append(head)
        return "\n".join(lines)

    @staticmethod
    def _format_run_context(rc: Optional[Dict[str, Any]]) -> str:
        if not rc:
            return ""
        bits = []
        if rc.get("run_id"):
            bits.append(f"run_id={rc['run_id']}")
        if rc.get("service"):
            bits.append(f"currently scanning {rc['service']}")
        if rc.get("findings_count"):
            bits.append(f"{rc['findings_count']} findings so far")
        if not bits:
            return ""
        return "Run context: " + ", ".join(bits) + ".\n"

    @staticmethod
    def _fallback_markdown(question: str, sources: List[QASource], reason: str) -> str:
        body = [
            "Hiện tại tôi chưa thể sinh câu trả lời do lỗi tạm thời ở LLM service.",
            f"_Lỗi:_ `{reason[:200]}`",
        ]
        if sources:
            body.append("\n**Các check liên quan có thể giúp bạn:**")
            for i, s in enumerate(sources[:3], start=1):
                body.append(f"- `{s.check_id or '—'}` — {s.title}")
        else:
            body.append("\nThử lại sau, hoặc gõ `scan <service>` để chạy pipeline PDCA.")
        return "\n".join(body)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(s: Optional[str], n: int) -> Optional[str]:
    if not s:
        return None
    s = str(s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


__all__ = ["QAAgent", "QAAnswer", "QASource", "asdict"]
