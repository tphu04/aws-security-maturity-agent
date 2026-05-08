"""Centralized config — Pydantic v2 BaseSettings.

Single source of truth cho mọi service URL, timeout, feature flag.
Đọc từ environment vars hoặc `.env` file.

NOTE: Yêu cầu `pydantic-settings>=2.0` trong requirements.txt (decision #29).
"""

from typing import List, Literal, Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ------------------------------------------------------------------
    # Service URLs
    # ------------------------------------------------------------------
    rag_api_url: str = "http://localhost:9005"
    scanner_api_url: str = "http://127.0.0.1:9001"

    # OLLAMA_URL alias cho backward-compat với .env cũ (decision #30)
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "OLLAMA_URL"),
    )
    ollama_model: str = "gemma3:4b"
    ollama_api_key: str = "ollama"

    # ------------------------------------------------------------------
    # Timeouts & limits
    # ------------------------------------------------------------------
    llm_timeout_s: float = 60.0
    rag_timeout_s: float = 10.0
    poll_max_iterations: int = 60
    poll_interval_s: float = 5.0
    poll_timeout_s: float = 300.0

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------
    multi_query_mode: bool = False

    # ------------------------------------------------------------------
    # Scanner whitelist (B17) — None = no filter (allow tất cả Prowler groups)
    # ------------------------------------------------------------------
    scanner_allowed_services: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # AWS (dùng cho api_server.py — Phase D)
    # ------------------------------------------------------------------
    aws_profile: str = "default"
    aws_default_region: str = "us-east-1"

    # ------------------------------------------------------------------
    # Scanner API behaviour (Phase D)
    # ------------------------------------------------------------------
    cleanup_scan_output: bool = True
    cors_origins: List[str] = ["*"]            # Dev: allow all; Prod: explicit list
    cors_allow_credentials: bool = False       # AUTO-OVERRIDE nếu cors_origins=["*"]

    # ------------------------------------------------------------------
    # Langfuse observability (Phase F foundation; disabled by default)
    # ------------------------------------------------------------------
    langfuse_enabled: bool = False
    langfuse_secret_key: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_redact_mode: Literal["full", "internal", "off"] = "full"
    langfuse_environment: Literal["dev", "staging", "prod"] = "dev"
    langfuse_flush_at_node: bool = True
    langfuse_circuit_breaker_threshold: int = 5
    langfuse_circuit_breaker_window_s: int = 60
    langfuse_bench_enabled: bool = False
    langfuse_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    langfuse_request_timeout_s: float = Field(default=2.0, gt=0.0)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _enforce_cors_spec(self) -> "Settings":
        """CORS spec: wildcard origins KHÔNG được kết hợp với credentials.
        Browser block request nếu vi phạm. Force credentials=False khi wildcard.
        """
        if "*" in self.cors_origins and self.cors_allow_credentials:
            import warnings

            warnings.warn(
                "cors_origins=['*'] không tương thích allow_credentials=True "
                "(CORS spec). Forcing cors_allow_credentials=False. "
                "Để bật credentials, set cors_origins thành explicit domain list."
            )
            object.__setattr__(self, "cors_allow_credentials", False)
        return self

    @model_validator(mode="after")
    def _enforce_langfuse_fail_safe(self) -> "Settings":
        """Langfuse is best-effort: missing credentials disables it safely."""
        if self.langfuse_enabled and (
            not self.langfuse_public_key or not self.langfuse_secret_key
        ):
            import warnings

            warnings.warn(
                "LANGFUSE_ENABLED=true nhưng thiếu LANGFUSE_PUBLIC_KEY hoặc "
                "LANGFUSE_SECRET_KEY. Forcing langfuse_enabled=False."
            )
            object.__setattr__(self, "langfuse_enabled", False)
        return self


settings = Settings()
