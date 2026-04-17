"""Post-generation fact validation for LLM-authored report sections.

Catches hallucinated numbers by checking that every integer/percent the model
writes matches an allowed value derived from the underlying data. Sections that
don't need numeric coverage (pure prose) can opt out.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape

logger = logging.getLogger(__name__)

# Extract integers and percentages from prose (not CSS/hex values inside HTML).
# We strip HTML tags first, so regex just needs to find numbers in plain text.
_NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,5})(?:[.,](\d{1,2}))?\s*%?")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ValidationResult:
    ok: bool
    offending: list[str]

    def __bool__(self) -> bool:
        return self.ok


class FactValidator:
    """Assert that numbers in LLM output belong to an allowed set.

    `tolerance`: numbers rounded to nearest integer must match; e.g. "73.7%"
    is allowed if `73` or `74` is in the allowed set (we check both floor/ceil
    of the percent number). Stage/year-like small numbers (< `ignore_below`)
    are skipped because small integers are often quantifiers ("3 lỗ hổng")
    rather than data claims.
    """

    def __init__(self, ignore_below: int = 5, tolerance: float = 0.5):
        self.ignore_below = ignore_below
        self.tolerance = tolerance

    @staticmethod
    def _strip_html(text: str) -> str:
        return unescape(_TAG_RE.sub(" ", text))

    def _extract_numbers(self, text: str) -> list[float]:
        plain = self._strip_html(text)
        found: list[float] = []
        for m in _NUMBER_RE.finditer(plain):
            whole, frac = m.group(1), m.group(2)
            try:
                val = float(whole) if not frac else float(f"{whole}.{frac}")
            except ValueError:
                continue
            found.append(val)
        return found

    def validate(self, text: str, allowed: set[float]) -> ValidationResult:
        """Return `ValidationResult(ok=False, offending=[...])` if any number
        in `text` is not in `allowed` (± tolerance). Numbers below
        `ignore_below` are skipped.
        """
        if not text:
            return ValidationResult(True, [])

        # Normalize allowed: also accept floor/ceil of each allowed value
        expanded: set[int] = set()
        for v in allowed:
            expanded.add(int(v))
            expanded.add(int(v + 0.5))
            expanded.add(int(v + 0.999))

        offending: list[str] = []
        for n in self._extract_numbers(text):
            if n < self.ignore_below:
                continue
            as_int = int(n)
            if as_int in expanded:
                continue
            # Accept if within tolerance of any allowed
            if any(abs(n - a) <= self.tolerance for a in allowed):
                continue
            offending.append(str(n if n != as_int else as_int))

        if offending:
            return ValidationResult(False, offending)
        return ValidationResult(True, [])


def collect_allowed_numbers(data: dict, fields: list[str]) -> set[float]:
    """Walk `data` dot-paths and collect numeric leaves."""
    allowed: set[float] = set()
    for path in fields:
        cur = data
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and isinstance(cur, (int, float)):
            allowed.add(float(cur))
    return allowed
