"""Concrete LLM adapters for `LLMProposer`.

Two backends are supported, picked by environment:
  - Anthropic (ANTHROPIC_API_KEY)  -> Claude
  - OpenAI    (OPENAI_API_KEY)     -> GPT

Adapters share a tiny contract: `(system: str, human: str) -> str` that
returns the assistant's content. This keeps `LLMProposer` SDK-agnostic.

A persistent JSON cache (`.cache/llm_proposer_cache.json`) avoids re-calling
the model on identical (system, human, model_id) tuples. The cache key
hashes the prompt + model id, so changing either invalidates entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class PromptCache:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    @staticmethod
    def key(model_id: str, system: str, human: str) -> str:
        h = hashlib.sha256()
        h.update(model_id.encode())
        h.update(b"\x00")
        h.update(system.encode())
        h.update(b"\x00")
        h.update(human.encode())
        return h.hexdigest()

    def get(self, k: str) -> Optional[str]:
        return self._data.get(k)

    def set(self, k: str, v: str) -> None:
        self._data[k] = v
        # Write-through is fine here — calls are not hot-path.
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False), encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

def make_anthropic_invoke(
    *,
    model: str = "claude-opus-4-7",
    api_key: Optional[str] = None,
    max_tokens: int = 1024,
    cache: Optional[PromptCache] = None,
    retries: int = 2,
) -> Callable[[str, str], str]:
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise ImportError(
            "anthropic SDK is required for Anthropic adapter. "
            "Install with: pip install anthropic"
        ) from e

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = Anthropic(api_key=key)

    def invoke(system: str, human: str) -> str:
        if cache:
            ck = cache.key(model, system, human)
            cached = cache.get(ck)
            if cached is not None:
                return cached
        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": human}],
                )
                content = "".join(
                    block.text for block in resp.content
                    if getattr(block, "type", None) == "text"
                )
                if cache:
                    cache.set(cache.key(model, system, human), content)
                return content
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"Anthropic call failed: {last_err}")

    return invoke


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

def make_openai_invoke(
    *,
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
    max_tokens: int = 1024,
    cache: Optional[PromptCache] = None,
    retries: int = 2,
) -> Callable[[str, str], str]:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "openai SDK is required for OpenAI adapter. "
            "Install with: pip install openai"
        ) from e

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=key)

    def invoke(system: str, human: str) -> str:
        if cache:
            ck = cache.key(model, system, human)
            cached = cache.get(ck)
            if cached is not None:
                return cached
        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": human},
                    ],
                )
                content = resp.choices[0].message.content or ""
                if cache:
                    cache.set(cache.key(model, system, human), content)
                return content
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"OpenAI call failed: {last_err}")

    return invoke


# ---------------------------------------------------------------------------
# Auto-select from env
# ---------------------------------------------------------------------------

def make_invoke_from_env(
    cache: Optional[PromptCache] = None,
) -> tuple[Callable[[str, str], str], str]:
    """Return (invoke_fn, model_id) using whichever provider has a key set.

    Preference order: Anthropic > OpenAI. Raises if neither is configured.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
        return make_anthropic_invoke(model=model, cache=cache), model
    if os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return make_openai_invoke(model=model, cache=cache), model
    raise RuntimeError(
        "Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set. "
        "Set one to enable LLMProposer."
    )
