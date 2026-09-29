"""Bootstrap confidence intervals and paired comparisons."""

from __future__ import annotations

import random


def bootstrap_ci(values: list[float], n_boot: int = 5000, alpha: float = 0.05, seed: int = 7) -> dict:
    """Percentile bootstrap CI for the mean of values (booleans count as 0/1)."""
    xs = [float(v) for v in values if v is not None]
    if not xs:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    rng = random.Random(seed)
    n = len(xs)
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return {"mean": round(sum(xs) / n, 4), "lo": round(lo, 4), "hi": round(hi, 4), "n": n}


def paired_diff(a: dict[str, float], b: dict[str, float], n_boot: int = 5000, seed: int = 7) -> dict:
    """Bootstrap CI of mean(b - a) over items present in both. Positive means b is higher."""
    keys = sorted(set(a) & set(b))
    if not keys:
        return {"diff": None, "lo": None, "hi": None, "n": 0, "within_noise": None}
    d = [float(b[k]) - float(a[k]) for k in keys]
    ci = bootstrap_ci(d, n_boot=n_boot, seed=seed)
    within = ci["lo"] <= 0 <= ci["hi"]
    return {"diff": ci["mean"], "lo": ci["lo"], "hi": ci["hi"], "n": len(keys), "within_noise": within}


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    if not a or len(a) != len(b):
        return None
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0
