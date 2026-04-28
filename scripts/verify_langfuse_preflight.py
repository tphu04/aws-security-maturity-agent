"""Phase Pre-Flight verification script for Langfuse integration.

Chạy script này trước khi bắt đầu Phase F (Foundation) để confirm môi trường
đã sẵn sàng. Re-runnable — không side-effect ngoài stdout output.

Usage:
    python scripts/verify_langfuse_preflight.py

Mapping về task trong docs/LANGFUSE_IMPLEMENTATION_PLAN.md §0:
    P0.1 — Langfuse credentials (manual, chỉ check env var presence).
    P0.2 — langchain-ollama usage_metadata available.
    P0.3 — git working tree clean.
    P0.4 — checkpoint DB backup tồn tại.
    P0.5 — branch hiện tại (informational).
    P0.6 — Python >= 3.12.

Exit code:
    0 — tất cả pass HOẶC chỉ thiếu credentials (warn).
    1 — có check fail blocking Phase F.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Windows cp1252 console không hỗ trợ tiếng Việt — force UTF-8 cho stdout/stderr.
# `reconfigure` có sẵn trên Python 3.7+, no-op trên môi trường đã UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Output helpers — stdlib only, no color dep
# ---------------------------------------------------------------------------


def _ok(msg: str) -> None:
    print(f"[ OK  ] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN ] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL ] {msg}")


def _info(msg: str) -> None:
    print(f"[INFO ] {msg}")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_python_version() -> bool:
    """P0.6 — Python >= 3.12."""
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 12):
        _ok(f"P0.6 Python {major}.{minor} >= 3.12")
        return True
    _fail(f"P0.6 Python {major}.{minor} < 3.12 — upgrade required")
    return False


def check_git_clean() -> bool:
    """P0.3 — git working tree clean (no modified tracked files).

    Untracked files OK (dev artifacts, new docs). Modified files NOT OK —
    có thể conflict khi tạo branch Phase F.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _fail(f"P0.3 git not available or not a repo: {e}")
        return False

    modified = [
        line for line in result.stdout.splitlines() if line and line[0] in "MARCD"
    ]
    if not modified:
        _ok("P0.3 git working tree clean (no modified tracked files)")
        return True
    _fail("P0.3 git has modified files — commit or stash before Phase F:")
    for line in modified[:10]:
        print(f"        {line}")
    return False


def check_current_branch() -> bool:
    """P0.5 — informational: current branch."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        _info(
            f"P0.5 current branch: '{branch}'. "
            "Tạo 'feat/langfuse-foundation' khi bắt đầu Phase F."
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        _warn("P0.5 cannot read git branch")
        return True  # not blocking


def check_langchain_ollama_usage_metadata() -> bool:
    """P0.2 — langchain-ollama exposes usage_metadata field.

    KHÔNG instantiate ChatOllama (yêu cầu Ollama server) — chỉ kiểm
    source code có handle field hay không. Đủ để gate Phase F.
    """
    try:
        import langchain
        import langchain_core
        import langchain_ollama
    except ImportError as e:
        _fail(f"P0.2 missing dep: {e}")
        return False

    _info(
        f"P0.2 langchain={langchain.__version__}, "
        f"core={langchain_core.__version__}, "
        f"ollama={langchain_ollama.__version__}"
    )

    try:
        import inspect

        from langchain_ollama import ChatOllama

        src = inspect.getsource(ChatOllama)
    except Exception as e:
        _fail(f"P0.2 cannot inspect ChatOllama: {e}")
        return False

    has_usage_metadata = "usage_metadata" in src
    has_eval_count = "eval_count" in src
    has_input_tokens = "input_tokens" in src

    if has_usage_metadata and has_eval_count and has_input_tokens:
        _ok(
            "P0.2 ChatOllama source has usage_metadata + eval_count + input_tokens"
        )
        return True
    _fail(
        "P0.2 ChatOllama missing token fields — "
        f"usage_metadata={has_usage_metadata}, "
        f"eval_count={has_eval_count}, "
        f"input_tokens={has_input_tokens}"
    )
    return False


def check_checkpoint_backup() -> bool:
    """P0.4 — backup folder cho SqliteSaver checkpoint."""
    ckpt_dir = PROJECT_ROOT / "data" / "checkpoints"
    backup_dir = ckpt_dir / "backups"

    if not ckpt_dir.exists():
        _info("P0.4 no checkpoints dir — first-run scenario, skip backup")
        return True

    db_files = list(ckpt_dir.glob("*.db"))
    if not db_files:
        _info("P0.4 no .db files — nothing to backup")
        return True

    if not backup_dir.exists() or not list(backup_dir.glob("*.db")):
        _warn(
            "P0.4 checkpoint .db files exist but no backup found — "
            "run: cp data/checkpoints/*.db data/checkpoints/backups/"
        )
        return False
    _ok(
        f"P0.4 backup folder exists with "
        f"{len(list(backup_dir.glob('*.db')))} backup file(s)"
    )
    return True


def check_langfuse_credentials() -> bool:
    """P0.1 — Langfuse credentials present.

    Không bắt buộc cho Phase F (LANGFUSE_ENABLED default False). Chỉ warn.
    """
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sec = os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = os.environ.get("LANGFUSE_HOST", "")

    if pub and sec:
        host_display = host or "https://cloud.langfuse.com (default)"
        _ok(f"P0.1 Langfuse keys present, host={host_display}")
        return True
    _warn(
        "P0.1 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set — "
        "OK cho Phase F (default disabled), bắt buộc cho Phase I E2E test"
    )
    return True  # not blocking Phase F


def check_langfuse_sdk_installed() -> bool:
    """Bonus — Langfuse SDK installed (cho Phase F.1 sẽ thêm)."""
    try:
        import langfuse  # noqa: F401

        _ok(f"Langfuse SDK installed: {langfuse.__version__}")
        return True
    except ImportError:
        _info(
            "Langfuse SDK NOT installed — sẽ thêm vào requirements.txt ở Phase F.1"
        )
        return True  # expected at Pre-Flight


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

CHECKS = [
    ("Python version", check_python_version, True),
    ("Git working tree", check_git_clean, True),
    ("Current branch (info)", check_current_branch, False),
    ("langchain-ollama usage_metadata", check_langchain_ollama_usage_metadata, True),
    ("Checkpoint backup", check_checkpoint_backup, False),
    ("Langfuse credentials", check_langfuse_credentials, False),
    ("Langfuse SDK installed", check_langfuse_sdk_installed, False),
]


def main() -> int:
    print("=" * 70)
    print(" Langfuse Pre-Flight verification — docs/LANGFUSE_IMPLEMENTATION_PLAN.md §0")
    print("=" * 70)

    failed_blocking = 0
    for label, fn, blocking in CHECKS:
        print(f"\n--- {label} ---")
        try:
            ok = fn()
        except Exception as e:  # defensive — verification script must not crash
            _fail(f"unexpected error: {e}")
            ok = False
        if not ok and blocking:
            failed_blocking += 1

    print("\n" + "=" * 70)
    if failed_blocking == 0:
        print(" RESULT: Pre-Flight PASSED — sẵn sàng bắt đầu Phase F")
        print("=" * 70)
        return 0
    print(f" RESULT: Pre-Flight FAILED — {failed_blocking} blocking check(s) thất bại")
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main())
