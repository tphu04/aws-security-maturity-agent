from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import (
    DATA_ROOT,
    PROWLER_RAW_PATH,
    MATURITY_RAW_PATH,
    MAPPINGS_RAW_PATH,
)


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"raw data file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_prowler_raw(path: Path | None = None) -> List[Dict[str, Any]]:
    target = Path(path or PROWLER_RAW_PATH)
    payload = load_json(target)
    if not isinstance(payload, list):
        raise ValueError(
            f"expected prowler raw payload to be a list, got: {type(payload).__name__}"
        )
    return payload


def load_maturity_raw(path: Path | None = None) -> List[Dict[str, Any]]:
    target = Path(path or MATURITY_RAW_PATH)
    payload = load_json(target)

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return payload["items"]
        if isinstance(payload.get("capabilities"), list):
            return payload["capabilities"]

    raise ValueError(
        f"unsupported maturity raw payload shape: {type(payload).__name__}"
    )


def load_mappings_raw(path: Path | None = None) -> List[Dict[str, Any]]:
    target = Path(path or MAPPINGS_RAW_PATH)
    payload = load_json(target)
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return payload["items"]

    raise ValueError(
        f"expected mappings raw payload to be a list, got: {type(payload).__name__}"
    )
