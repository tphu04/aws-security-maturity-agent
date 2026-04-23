"""LLM-Judge module for Report Agent Evaluation v3.

Two judges, both deterministic-ish via ``temperature=0.3`` + pinned seed:

* :class:`FaithfulnessJudge`  — RAGAS-style claim decomposition.
* :class:`ActionabilityJudge` — G-Eval Likert (1–5) on recommendation
  executability, with chain-of-thought.

Provider abstraction (``call_llm``) is currently wired to Groq only —
Gemini free tier was reduced to 20 RPD in 2026 which is insufficient for
240-call ablation runs, so the module keeps only the provider that can
actually serve that volume. Other provider implementations (Gemini,
OpenRouter, Ollama) are kept in the source for reference but excluded
from ``_PROVIDERS``.

Env vars read:
    GROQ_API_KEY, GROQ_MODEL   — primary (active)
    GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_ENDPOINT   — reference only
    OPENROUTER_API_KEY, OPENROUTER_MODEL            — reference only
    OLLAMA_URL, OLLAMA_MODEL                        — reference only
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import pdca.config so python-dotenv loads .env (GOOGLE_API_KEY, etc.)
try:
    import pdca.config  # noqa: F401
except Exception:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "benchmark_outputs" / "judge_cache"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post_json(
    url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float = 60.0,
) -> Dict[str, Any]:
    """POST JSON body; inject a browser-like User-Agent if the caller
    didn't provide one. Several provider endpoints (notably Groq, which
    sits behind Cloudflare) return ``403 error code 1010`` when the
    default ``Python-urllib/X.Y`` UA is used. A realistic UA bypasses
    that bot-filter without otherwise affecting request semantics.
    """
    merged_headers = dict(headers or {})
    merged_headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (benchmark-report-judge/1.0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    )
    merged_headers.setdefault("Accept", "application/json")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=merged_headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class ProviderError(RuntimeError):
    """Raised when a specific provider cannot be reached or returns an error."""


# Rate-limit state for Gemini free tier (10 RPM). A module-level timestamp
# enforces a minimum interval between outgoing requests so back-to-back
# judge calls do not hammer the quota and fail with 429.
_GEMINI_MIN_INTERVAL_S = 5.0
_gemini_last_call_ts = 0.0


def _gemini_rate_limit_wait() -> None:
    """Block until it is safe to issue the next Gemini request."""
    global _gemini_last_call_ts
    now = time.monotonic()
    wait = _GEMINI_MIN_INTERVAL_S - (now - _gemini_last_call_ts)
    if wait > 0:
        time.sleep(wait)
    _gemini_last_call_ts = time.monotonic()


# Rate-limit state for Groq free tier. The `openai/gpt-oss-20b` model on
# Groq free tier is capped at 30 RPM; 2.5s between calls keeps us safely
# under that ceiling while finishing 240 calls in roughly 10 minutes.
_GROQ_MIN_INTERVAL_S = 2.5
_groq_last_call_ts = 0.0


def _groq_rate_limit_wait() -> None:
    """Block until it is safe to issue the next Groq request."""
    global _groq_last_call_ts
    now = time.monotonic()
    wait = _GROQ_MIN_INTERVAL_S - (now - _groq_last_call_ts)
    if wait > 0:
        time.sleep(wait)
    _groq_last_call_ts = time.monotonic()


def _call_gemini(prompt: str, temperature: float, seed: int) -> Tuple[str, str]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ProviderError("GOOGLE_API_KEY not set")
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    endpoint = os.getenv(
        "GEMINI_ENDPOINT",
        "https://generativelanguage.googleapis.com/v1beta/models",
    ).rstrip("/")
    url = f"{endpoint}/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "candidateCount": 1,
            "maxOutputTokens": 1024,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key,
    }
    # Retry loop for 429 (rate-limit). Gemini free tier = 10 RPM; we enforce
    # a minimum interval BEFORE each call, and back off up to 3 times if the
    # server still says we're over quota.
    max_retries = 3
    backoff = 30.0
    last_err: Optional[str] = None
    for attempt in range(max_retries + 1):
        _gemini_rate_limit_wait()
        try:
            resp = _post_json(url, payload, headers)
            break
        except urllib.error.HTTPError as e:
            body = e.read()[:200]
            if e.code == 429 and attempt < max_retries:
                logger.info("gemini 429 — sleeping %.0fs (attempt %d/%d)",
                            backoff, attempt + 1, max_retries)
                time.sleep(backoff)
                backoff *= 1.5
                last_err = f"gemini HTTP 429: {body!r}"
                continue
            raise ProviderError(f"gemini HTTP {e.code}: {body!r}")
        except Exception as e:
            raise ProviderError(f"gemini error: {e}")
    else:
        raise ProviderError(last_err or "gemini retries exhausted")
    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"gemini unexpected payload: {resp!r}") from e
    return text, f"gemini/{model}"


def _call_openrouter(prompt: str, temperature: float, seed: int) -> Tuple[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ProviderError("OPENROUTER_API_KEY not set")
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "seed": seed,
        "max_tokens": 1024,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    try:
        resp = _post_json(url, payload, headers)
    except urllib.error.HTTPError as e:
        raise ProviderError(f"openrouter HTTP {e.code}: {e.read()[:200]!r}")
    except Exception as e:
        raise ProviderError(f"openrouter error: {e}")
    try:
        text = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"openrouter unexpected payload: {resp!r}") from e
    return text, f"openrouter/{model}"


def _call_ollama(prompt: str, temperature: float, seed: int) -> Tuple[str, str]:
    base_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "seed": seed,
        },
    }
    headers = {"Content-Type": "application/json"}
    try:
        resp = _post_json(url, payload, headers, timeout=120.0)
    except urllib.error.HTTPError as e:
        raise ProviderError(f"ollama HTTP {e.code}: {e.read()[:200]!r}")
    except Exception as e:
        raise ProviderError(f"ollama error: {e}")
    text = (resp.get("message") or {}).get("content") or ""
    if not text:
        raise ProviderError(f"ollama empty response: {resp!r}")
    return text, f"ollama/{model}"


def _call_groq(prompt: str, temperature: float, seed: int) -> Tuple[str, str]:
    """Call Groq OpenAI-compatible chat completions endpoint.

    Defaults to ``openai/gpt-oss-20b`` (non-Llama family per LVTN
    requirement) — OpenAI's 120B open-weight model hosted on Groq. The
    model emits separate ``reasoning`` tokens that do not show up as
    content, so ``max_tokens`` is sized generously (2048) to leave room
    for both reasoning and the JSON payload the judge expects.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ProviderError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "seed": seed,
        "max_tokens": 2048,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    max_retries = 3
    backoff = 30.0
    last_err: Optional[str] = None
    for attempt in range(max_retries + 1):
        _groq_rate_limit_wait()
        try:
            resp = _post_json(url, payload, headers, timeout=120.0)
            break
        except urllib.error.HTTPError as e:
            body = e.read()[:200]
            if e.code == 429 and attempt < max_retries:
                logger.info("groq 429 — sleeping %.0fs (attempt %d/%d)",
                            backoff, attempt + 1, max_retries)
                time.sleep(backoff)
                backoff *= 1.5
                last_err = f"groq HTTP 429: {body!r}"
                continue
            raise ProviderError(f"groq HTTP {e.code}: {body!r}")
        except Exception as e:
            raise ProviderError(f"groq error: {e}")
    else:
        raise ProviderError(last_err or "groq retries exhausted")
    try:
        text = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"groq unexpected payload: {resp!r}") from e
    if not text:
        # gpt-oss-120b emits a "reasoning" field separately. If content is
        # empty but reasoning is populated, surface the reasoning text —
        # better than raising and losing a slow call.
        reasoning = (
            (resp.get("choices") or [{}])[0]
            .get("message", {})
            .get("reasoning")
            or ""
        )
        if reasoning:
            text = reasoning
        else:
            raise ProviderError(f"groq empty response: {resp!r}")
    return text, f"groq/{model}"


# Groq-only mode for LVTN reproducibility. Gemini free tier was reduced
# to 20 RPD in 2026 which is insufficient for 240 judge calls in a single
# ablation run, so the provider chain is locked to Groq. No fallback —
# self-evaluation on Ollama gemma3:4b is not defensible for a thesis
# evaluation; if Groq is unreachable the caller sees the error directly.
_PROVIDERS = [
    ("groq", _call_groq),
]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class JudgeCache:
    """Disk-backed cache keyed by sha256(provider + model + prompt + seed + temp)."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _key(self, prompt: str, temperature: float, seed: int) -> str:
        material = "\n".join([
            os.getenv("GOOGLE_API_KEY", "")[-4:],  # fingerprint, not value
            os.getenv("GEMINI_MODEL", ""),
            os.getenv("GROQ_MODEL", ""),
            os.getenv("OPENROUTER_MODEL", ""),
            os.getenv("OLLAMA_MODEL", ""),
            f"{temperature:.3f}",
            str(seed),
            prompt,
        ])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(self, prompt: str, temperature: float, seed: int) -> Optional[Dict[str, Any]]:
        key = self._key(prompt, temperature, seed)
        path = self.dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def put(
        self, prompt: str, temperature: float, seed: int,
        response_text: str, provider: str,
    ) -> None:
        key = self._key(prompt, temperature, seed)
        path = self.dir / f"{key}.json"
        path.write_text(
            json.dumps({
                "prompt_sha256": key,
                "provider": provider,
                "temperature": temperature,
                "seed": seed,
                "response_text": response_text,
                "cached_at": time.time(),
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Top-level LLM call
# ---------------------------------------------------------------------------

def call_llm(
    prompt: str,
    *,
    temperature: float = 0.3,
    seed: int = 42,
    cache: Optional[JudgeCache] = None,
) -> Tuple[str, str]:
    """Return ``(response_text, provider_label)``.

    Tries providers in ``_PROVIDERS`` order; returns the first success.
    Uses ``cache`` when provided. Raises :class:`ProviderError` if every
    provider fails.
    """
    if cache is not None:
        cached = cache.get(prompt, temperature, seed)
        if cached is not None:
            return cached["response_text"], f"cache:{cached.get('provider','?')}"

    last_err: Optional[Exception] = None
    for name, fn in _PROVIDERS:
        try:
            text, provider = fn(prompt, temperature, seed)
            if cache is not None:
                cache.put(prompt, temperature, seed, text, provider)
            return text, provider
        except ProviderError as e:
            logger.info("provider %s failed: %s", name, e)
            last_err = e
            continue
    raise ProviderError(f"all providers failed; last: {last_err}")


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort pull a JSON object out of a free-form LLM response."""
    if not text:
        return None
    # Strip ```json / ``` fences first.
    stripped = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    # Greedy match: whole span between first '{' and last '}'.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = stripped[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Try a narrower match.
        m = _JSON_BLOCK_RE.search(stripped)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


# ---------------------------------------------------------------------------
# Judge base
# ---------------------------------------------------------------------------

@dataclass
class JudgeResult:
    score: Optional[float]
    samples: List[Dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    parse_errors: int = 0
    raw_score_std: Optional[float] = None  # sample variance for transparency


class _BaseJudge:
    name: str = "base"

    def __init__(
        self,
        cache: Optional[JudgeCache] = None,
        samples: int = 2,
        temperature: float = 0.3,
        base_seed: int = 42,
    ):
        self.cache = cache if cache is not None else JudgeCache()
        self.samples = samples
        self.temperature = temperature
        self.base_seed = base_seed

    # Subclasses must implement these.
    def build_prompt(self, **kwargs: Any) -> str:  # pragma: no cover
        raise NotImplementedError

    def parse(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def score_from_parsed(self, parsed: Dict[str, Any]) -> Optional[float]:  # pragma: no cover
        raise NotImplementedError

    def run(self, **kwargs: Any) -> JudgeResult:
        prompt = self.build_prompt(**kwargs)
        sample_results: List[Dict[str, Any]] = []
        parse_errors = 0
        provider_used = ""
        for i in range(self.samples):
            seed = self.base_seed + i
            try:
                raw, provider = call_llm(
                    prompt, temperature=self.temperature, seed=seed,
                    cache=self.cache,
                )
            except ProviderError as e:
                logger.warning("%s: all providers failed for seed %d: %s",
                               self.name, seed, e)
                parse_errors += 1
                sample_results.append({"seed": seed, "error": str(e)})
                continue
            provider_used = provider_used or provider
            parsed = _extract_json(raw)
            if parsed is None:
                parse_errors += 1
                sample_results.append({
                    "seed": seed, "provider": provider,
                    "parse_error": True, "raw_excerpt": raw[:200],
                })
                continue
            parsed = self.parse(parsed) or {}
            score = self.score_from_parsed(parsed)
            sample_results.append({
                "seed": seed, "provider": provider,
                "parsed": parsed, "score": score,
            })

        # Aggregate.
        scores = [s["score"] for s in sample_results
                  if isinstance(s.get("score"), (int, float))]
        if scores:
            mean = sum(scores) / len(scores)
            if len(scores) > 1:
                m = mean
                var = sum((x - m) ** 2 for x in scores) / (len(scores) - 1)
                std = var ** 0.5
            else:
                std = 0.0
        else:
            mean = None
            std = None
        return JudgeResult(
            score=round(mean, 4) if mean is not None else None,
            samples=sample_results,
            provider=provider_used,
            parse_errors=parse_errors,
            raw_score_std=round(std, 4) if std is not None else None,
        )


# ---------------------------------------------------------------------------
# FaithfulnessJudge — RAGAS-style
# ---------------------------------------------------------------------------

class FaithfulnessJudge(_BaseJudge):
    name = "faithfulness"

    _PROMPT_TEMPLATE = """You are an evaluator grading whether a security report narrative is FAITHFUL to its source evidence (RAG context + scan findings). Do not grade writing style — only factual grounding.

=== RAG CONTEXT ===
{rag_block}

=== SCAN FINDINGS (summary) ===
{findings_block}

=== REPORT NARRATIVE (to evaluate) ===
{narrative}

TASK
1. Decompose the narrative into 3-8 distinct factual claims (a claim is a statement about findings counts, severity, capabilities, remediation outcomes, risks, etc.).
2. For EACH claim, give a verdict:
   - "supported"   : the claim is directly entailed by RAG context or findings.
   - "unsupported" : the claim contradicts or invents facts not in RAG/findings.
   - "partial"     : the claim overstates or loosely paraphrases source material.
3. Compute overall_score = (#supported + 0.5 × #partial) / total_claims.

Respond with JSON ONLY (no prose, no code fences):
{{
  "claims": [
    {{"text": "...", "verdict": "supported|partial|unsupported", "reason": "one short sentence"}}
  ],
  "overall_score": 0.0
}}
"""

    def build_prompt(
        self, *, narrative: str, rag_context: Dict[str, Any],
        findings: List[Dict[str, Any]],
    ) -> str:
        rag_block = _format_rag_block(rag_context)
        findings_block = _format_findings_block(findings)
        # Trim narrative to keep total prompt ≤ ~6k tokens.
        narrative = narrative.strip()[:4000]
        return self._PROMPT_TEMPLATE.format(
            rag_block=rag_block or "(empty)",
            findings_block=findings_block or "(empty)",
            narrative=narrative or "(empty)",
        )

    def parse(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        claims = payload.get("claims")
        if not isinstance(claims, list):
            return None
        overall = payload.get("overall_score")
        if overall is None:
            # Re-compute from claim verdicts if the model omitted it.
            total = len(claims) or 1
            sup = sum(1 for c in claims if (c or {}).get("verdict") == "supported")
            par = sum(1 for c in claims if (c or {}).get("verdict") == "partial")
            overall = (sup + 0.5 * par) / total
        try:
            overall = float(overall)
        except (TypeError, ValueError):
            return None
        overall = max(0.0, min(1.0, overall))
        return {"claims": claims, "overall_score": overall}

    def score_from_parsed(self, parsed: Dict[str, Any]) -> Optional[float]:
        return parsed.get("overall_score")


# ---------------------------------------------------------------------------
# ActionabilityJudge — G-Eval Likert
# ---------------------------------------------------------------------------

class ActionabilityJudge(_BaseJudge):
    name = "actionability"

    _PROMPT_TEMPLATE = """You are an evaluator grading the ACTIONABILITY of security recommendations. A recommendation is actionable if a reader can execute it without further clarification (specific commands, config keys, resource names, measurable targets).

=== RAG RECOMMENDED PRACTICES (reference) ===
{practices_block}

=== RECOMMENDATIONS TO GRADE ===
{recommendations}

Use this 1–5 Likert rubric:
5 — Specific, executable steps or commands / config changes / measurable targets. A junior engineer can implement directly.
4 — Clear action verbs + named controls, but missing one of: exact commands, specific resource IDs, measurable criteria.
3 — Correct direction with named controls but lacking concrete steps (still requires operator judgment).
2 — Mostly vague guidance; mentions controls but no execution path.
1 — Vague platitudes ("strengthen security", "follow best practices") with no operator guidance.

Think step by step in "reasoning" (2-4 short sentences), then assign an integer 1-5.

Respond with JSON ONLY (no prose, no code fences):
{{
  "reasoning": "...",
  "likert": 3
}}
"""

    def build_prompt(
        self, *, recommendations: str, practices: List[str],
    ) -> str:
        practices_block = "\n".join(f"- {p}" for p in (practices or [])) or "(none)"
        recommendations = (recommendations or "").strip()[:4000] or "(empty)"
        return self._PROMPT_TEMPLATE.format(
            practices_block=practices_block,
            recommendations=recommendations,
        )

    def parse(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        likert = payload.get("likert")
        try:
            likert = int(round(float(likert)))
        except (TypeError, ValueError):
            return None
        if likert < 1 or likert > 5:
            return None
        return {
            "likert": likert,
            "reasoning": str(payload.get("reasoning") or "")[:500],
        }

    def score_from_parsed(self, parsed: Dict[str, Any]) -> Optional[float]:
        return float(parsed["likert"])


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_rag_block(rag_context: Dict[str, Any]) -> str:
    if not rag_context:
        return ""
    lines: List[str] = []
    topics = rag_context.get("primary_topics") or []
    if topics:
        lines.append("Primary topics: " + ", ".join(map(str, topics)))
    for d in (rag_context.get("capability_details") or [])[:6]:
        name = d.get("capability_name", "?")
        summary = d.get("summary", "")
        rec = d.get("recommendation", "")
        lines.append(f"- {name}: {summary} Recommendation: {rec}")
    practices = rag_context.get("recommended_practices") or []
    for p in practices[:6]:
        lines.append(f"- practice: {p}")
    conf = rag_context.get("confidence")
    if conf:
        lines.append(f"Confidence: {conf}")
    return "\n".join(lines)


def _format_findings_block(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return ""
    lines: List[str] = []
    for f in findings[:12]:
        sev = f.get("severity", "?")
        status = f.get("status", "?")
        desc = (f.get("description") or "")[:120]
        lines.append(f"- [{sev}/{status}] {desc}")
    if len(findings) > 12:
        lines.append(f"... and {len(findings) - 12} more findings")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Narrative extraction (LLM-authored sections only)
# ---------------------------------------------------------------------------

_NARRATIVE_SECTIONS = [
    (r"<h1>1\. Tóm tắt điều hành</h1>\s*(.*?)\s*<h1>", "executive_summary"),
    (r"<h3>Tổng quan các mục KHÔNG ĐẠT</h3>\s*(.*?)\s*<h1>", "fail_overview"),
    (r"<h2>6\.3 Đánh giá của chuyên gia</h2>\s*(.*?)\s*<h1>", "post_analysis"),
    # Template heading evolved from "7. Khuyến nghị chiến lược" to just
    # "7. Khuyến nghị"; match either, and terminate at the next top-level
    # heading / hr / body close so we don't miss the closing fence.
    (r"<h1>7\. Khuyến nghị[^<]*</h1>(.*?)(?:<hr\b|<h1>|</body>|$)",
     "recommendations"),
]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    from html import unescape
    return unescape(_TAG_RE.sub(" ", s or "")).strip()


def extract_narrative_for_judges(html: str) -> Dict[str, str]:
    """Return the LLM-written sections needed by the two judges."""
    out: Dict[str, str] = {}
    for pat, name in _NARRATIVE_SECTIONS:
        m = re.search(pat, html, re.DOTALL)
        if m:
            out[name] = _strip_html(m.group(1))
    return out


# ---------------------------------------------------------------------------
# Top-level per-case scoring
# ---------------------------------------------------------------------------

def judge_case(
    html: str,
    *,
    rag_context: Dict[str, Any],
    findings: List[Dict[str, Any]],
    cache: Optional[JudgeCache] = None,
    samples: int = 2,
) -> Dict[str, Any]:
    """Run both judges on a single case's HTML; return per-judge results."""
    cache = cache or JudgeCache()
    faithful = FaithfulnessJudge(cache=cache, samples=samples)
    actionable = ActionabilityJudge(cache=cache, samples=samples)

    sections = extract_narrative_for_judges(html)
    narrative = " ".join(
        sections.get(k, "") for k in
        ("executive_summary", "fail_overview", "post_analysis")
    ).strip()
    recommendations_text = sections.get("recommendations", "")

    if narrative:
        f_res = faithful.run(
            narrative=narrative,
            rag_context=rag_context,
            findings=findings,
        )
    else:
        f_res = JudgeResult(score=None, parse_errors=0,
                            samples=[{"skipped": "no narrative"}])

    if recommendations_text:
        a_res = actionable.run(
            recommendations=recommendations_text,
            practices=(rag_context or {}).get("recommended_practices") or [],
        )
    else:
        a_res = JudgeResult(score=None, parse_errors=0,
                            samples=[{"skipped": "no recommendations section"}])

    return {
        "claim_support_rate": {
            "score": f_res.score,
            "std": f_res.raw_score_std,
            "provider": f_res.provider,
            "parse_errors": f_res.parse_errors,
            "samples": f_res.samples,
        },
        "actionability_likert": {
            "score": a_res.score,
            "std": a_res.raw_score_std,
            "provider": a_res.provider,
            "parse_errors": a_res.parse_errors,
            "samples": a_res.samples,
        },
    }
