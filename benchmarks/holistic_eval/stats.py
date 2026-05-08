"""Statistical inference utilities for Chapter 6 evaluation tables.

Provides:
  - bootstrap_ci(values)            → mean + 95% CI (percentile bootstrap)
  - bootstrap_ci_mean_proportion()  → mean of binary outcomes + 95% CI
  - mcnemar_test(a_correct, b_correct)
        → exact McNemar p-value for paired binary outcomes (same items, two configs)
  - wilcoxon_paired(a, b)
        → Wilcoxon signed-rank p-value
  - qwk_with_ci(y_true, y_pred)
        → Quadratic Weighted Kappa + bootstrap CI
  - cv_with_ci(values)
        → Coefficient of variation + bootstrap CI

All functions are deterministic given a seed (default 42), pure Python where
possible, fall back to NumPy for QWK matrix arithmetic.
"""
from __future__ import annotations

import math
import random
from statistics import mean, stdev
from typing import Iterable, List, Sequence, Tuple

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover
    raise SystemExit("numpy required for stats.py") from exc

DEFAULT_N_BOOTSTRAP = 10_000
DEFAULT_ALPHA = 0.05
DEFAULT_SEED = 42


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------

def _percentile_ci(samples: Sequence[float], alpha: float) -> Tuple[float, float]:
    arr = sorted(samples)
    lo = arr[int((alpha / 2) * len(arr))]
    hi = arr[int((1 - alpha / 2) * len(arr)) - 1]
    return lo, hi


def bootstrap_ci(
    values: Sequence[float],
    n: int = DEFAULT_N_BOOTSTRAP,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Mean + 95% percentile-bootstrap CI for a continuous sample."""
    rng = random.Random(seed)
    k = len(values)
    if k == 0:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "n": 0}
    means = []
    vlist = list(values)
    for _ in range(n):
        sample = [vlist[rng.randrange(k)] for _ in range(k)]
        means.append(sum(sample) / k)
    lo, hi = _percentile_ci(means, alpha)
    return {
        "mean": sum(vlist) / k,
        "std": stdev(vlist) if k > 1 else 0.0,
        "ci_low": lo,
        "ci_high": hi,
        "n": k,
    }


def bootstrap_ci_proportion(
    successes: Sequence[int],  # 0/1 values
    n: int = DEFAULT_N_BOOTSTRAP,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Bootstrap CI for a proportion (mean of 0/1 outcomes)."""
    return bootstrap_ci(successes, n=n, alpha=alpha, seed=seed)


def cv_with_ci(values: Sequence[float], **kw) -> dict:
    """Coefficient of variation (std/mean) with bootstrap CI."""
    rng = random.Random(kw.get("seed", DEFAULT_SEED))
    k = len(values)
    if k < 2 or mean(values) == 0:
        return {"cv": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    cvs = []
    vlist = list(values)
    for _ in range(kw.get("n", DEFAULT_N_BOOTSTRAP)):
        sample = [vlist[rng.randrange(k)] for _ in range(k)]
        m = sum(sample) / k
        if m == 0:
            continue
        s = stdev(sample) if k > 1 else 0.0
        cvs.append(s / abs(m))
    cv_obs = stdev(vlist) / abs(mean(vlist))
    lo, hi = _percentile_ci(cvs, kw.get("alpha", DEFAULT_ALPHA))
    return {"cv": cv_obs, "ci_low": lo, "ci_high": hi, "n": k}


# ---------------------------------------------------------------------------
# Paired tests
# ---------------------------------------------------------------------------

def mcnemar_test(a_correct: Sequence[int], b_correct: Sequence[int]) -> dict:
    """Exact McNemar test for paired binary outcomes.

    a_correct[i], b_correct[i] in {0,1}: did config A / B classify item i correctly?
    Returns dict with discordant counts (b01, b10), test statistic, exact 2-sided p.
    Exact p uses the binomial distribution on min(b01,b10) ~ Binom(n_disc, 0.5).
    """
    if len(a_correct) != len(b_correct):
        raise ValueError("a_correct and b_correct must have same length")
    b01 = sum(1 for a, b in zip(a_correct, b_correct) if a == 0 and b == 1)
    b10 = sum(1 for a, b in zip(a_correct, b_correct) if a == 1 and b == 0)
    n_disc = b01 + b10
    if n_disc == 0:
        return {"b01": 0, "b10": 0, "n_discordant": 0, "p_value": 1.0, "method": "exact"}
    k = min(b01, b10)
    # 2-sided exact binomial p
    p = 0.0
    for i in range(k + 1):
        p += math.comb(n_disc, i) * 0.5 ** n_disc
    p = min(2 * p, 1.0)
    return {"b01": b01, "b10": b10, "n_discordant": n_disc, "p_value": p, "method": "exact"}


def wilcoxon_paired(a: Sequence[float], b: Sequence[float]) -> dict:
    """Approximate Wilcoxon signed-rank test for paired continuous data."""
    if len(a) != len(b):
        raise ValueError("a and b must have same length")
    diffs = [x - y for x, y in zip(a, b) if x != y]
    n = len(diffs)
    if n == 0:
        return {"n": 0, "p_value": 1.0, "W": 0}
    abs_diffs = [(abs(d), 1 if d > 0 else -1) for d in diffs]
    abs_diffs.sort(key=lambda t: t[0])
    # Average ranks for ties
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs_diffs[j + 1][0] == abs_diffs[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    w_plus = sum(r for r, (_, s) in zip(ranks, abs_diffs) if s > 0)
    w_minus = sum(r for r, (_, s) in zip(ranks, abs_diffs) if s < 0)
    W = min(w_plus, w_minus)
    # Normal approximation
    mu = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sigma == 0:
        return {"n": n, "p_value": 1.0, "W": W}
    z = (W - mu) / sigma
    # 2-sided p
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return {"n": n, "W": W, "z": z, "p_value": p}


# ---------------------------------------------------------------------------
# Quadratic Weighted Kappa
# ---------------------------------------------------------------------------

def quadratic_weighted_kappa(y_true: Sequence[int], y_pred: Sequence[int], n_classes: int = 4) -> float:
    """QWK for ordinal labels in [0, n_classes-1]."""
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    O = np.zeros((n_classes, n_classes), dtype=float)
    for t, p in zip(y_true, y_pred):
        O[t, p] += 1
    W = np.zeros_like(O)
    for i in range(n_classes):
        for j in range(n_classes):
            W[i, j] = ((i - j) ** 2) / ((n_classes - 1) ** 2)
    hist_t = O.sum(axis=1)
    hist_p = O.sum(axis=0)
    E = np.outer(hist_t, hist_p) / O.sum()
    num = (W * O).sum()
    den = (W * E).sum()
    if den == 0:
        return float("nan")
    return 1 - num / den


def qwk_with_ci(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    n_classes: int = 4,
    n: int = DEFAULT_N_BOOTSTRAP,
    alpha: float = DEFAULT_ALPHA,
    seed: int = DEFAULT_SEED,
) -> dict:
    """QWK with bootstrap CI."""
    rng = np.random.default_rng(seed)
    y_true = list(y_true)
    y_pred = list(y_pred)
    k = len(y_true)
    qwk_obs = quadratic_weighted_kappa(y_true, y_pred, n_classes)
    qwks = []
    idx_arr = np.arange(k)
    for _ in range(n):
        idx = rng.choice(idx_arr, size=k, replace=True)
        yt = [y_true[i] for i in idx]
        yp = [y_pred[i] for i in idx]
        try:
            q = quadratic_weighted_kappa(yt, yp, n_classes)
            if not math.isnan(q):
                qwks.append(q)
        except Exception:
            continue
    if not qwks:
        return {"qwk": qwk_obs, "ci_low": float("nan"), "ci_high": float("nan"), "n": k}
    lo, hi = _percentile_ci(qwks, alpha)
    return {"qwk": qwk_obs, "ci_low": lo, "ci_high": hi, "n": k}


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Toy example: 5 timing values
    times = [424.4, 513.9, 439.9, 391.0, 391.3]
    print("Timing 5 phiên D1:", bootstrap_ci(times))
    print("CV:", cv_with_ci(times))

    # Toy example: McNemar
    a = [1, 1, 0, 1, 1, 0, 1, 1, 1, 1]
    b = [1, 0, 1, 1, 1, 1, 1, 1, 1, 1]
    print("McNemar:", mcnemar_test(a, b))

    # Toy QWK
    y_true = [0, 0, 1, 2, 2, 3, 3, 1]
    y_pred = [0, 1, 1, 2, 1, 3, 2, 1]
    print("QWK:", qwk_with_ci(y_true, y_pred))
