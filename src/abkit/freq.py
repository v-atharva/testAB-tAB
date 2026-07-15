"""Frequentist readout for binomial (clicks/impressions) outcomes.

Two-proportion z-test, Wilson score intervals, Newcombe hybrid interval for
the absolute lift, Katz log interval for the relative lift, and a chi-square
omnibus test for k-arm experiments.

Design notes
------------
* CTRs here are ~1-2%, so normal-approximation Wald intervals are unreliable;
  Wilson/Newcombe are the defaults everywhere.
* Zero-click arms are legal inputs: Wilson handles k=0; the relative lift is
  reported as undefined (None) when either arm has zero clicks rather than
  returning an infinite or NaN interval.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats


@dataclass(frozen=True)
class ConfInt:
    lo: float
    hi: float


@dataclass(frozen=True)
class TwoPropResult:
    """Two-proportion z-test of H0: p1 == p0 (pooled variance, two-sided)."""

    z: float
    p_value: float


@dataclass(frozen=True)
class LiftEstimate:
    """Absolute and relative lift of a variant over a baseline.

    ``rel_lift``/``rel_ci`` are None when either arm has zero clicks
    (the ratio and its log-scale variance are undefined there).
    """

    abs_lift: float
    abs_ci: ConfInt
    rel_lift: float | None
    rel_ci: ConfInt | None


def _z_crit(alpha: float) -> float:
    return float(stats.norm.ppf(1.0 - alpha / 2.0))


def _validate_counts(k: int, n: int) -> None:
    if n <= 0:
        raise ValueError(f"impressions must be positive, got {n}")
    if not 0 <= k <= n:
        raise ValueError(f"clicks must be in [0, impressions], got k={k}, n={n}")


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> ConfInt:
    """Wilson score interval for a binomial proportion."""
    _validate_counts(k, n)
    z = _z_crit(alpha)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    radius = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = 0.0 if k == 0 else max(0.0, center - radius)  # exact endpoints at the
    hi = 1.0 if k == n else min(1.0, center + radius)  # boundary, no fp residue
    return ConfInt(lo, hi)


def two_prop_ztest(k1: int, n1: int, k0: int, n0: int) -> TwoPropResult:
    """Pooled two-proportion z-test, two-sided.

    Degenerate pooled rates (all clicks or none anywhere) give z=0, p=1:
    there is no evidence of a difference in either case.
    """
    _validate_counts(k1, n1)
    _validate_counts(k0, n0)
    pooled = (k1 + k0) / (n1 + n0)
    if pooled <= 0.0 or pooled >= 1.0:
        return TwoPropResult(z=0.0, p_value=1.0)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n0))
    z = (k1 / n1 - k0 / n0) / se
    p = 2.0 * float(stats.norm.sf(abs(z)))
    return TwoPropResult(z=z, p_value=min(1.0, p))


def newcombe_ci(k1: int, n1: int, k0: int, n0: int, alpha: float = 0.05) -> ConfInt:
    """Newcombe hybrid score interval for the difference p1 - p0.

    Combines the per-arm Wilson limits (Newcombe 1998, method 10); much better
    behaved than Wald at small proportions and with zero-click arms.
    """
    p1, p0 = k1 / n1, k0 / n0
    w1, w0 = wilson_ci(k1, n1, alpha), wilson_ci(k0, n0, alpha)
    d = p1 - p0
    lo = d - math.sqrt((p1 - w1.lo) ** 2 + (w0.hi - p0) ** 2)
    hi = d + math.sqrt((w1.hi - p1) ** 2 + (p0 - w0.lo) ** 2)
    return ConfInt(max(-1.0, lo), min(1.0, hi))


def relative_lift_ci(
    k1: int, n1: int, k0: int, n0: int, alpha: float = 0.05
) -> tuple[float, ConfInt] | None:
    """Relative lift (risk ratio - 1) with a Katz log-scale interval.

    Returns None when either arm has zero clicks: the point estimate is then
    0%, -100%, or infinite and the log-variance is undefined — the readout
    layer reports this state explicitly instead of inventing a number.
    """
    _validate_counts(k1, n1)
    _validate_counts(k0, n0)
    if k1 == 0 or k0 == 0:
        return None
    rr = (k1 / n1) / (k0 / n0)
    se_log = math.sqrt(1 / k1 - 1 / n1 + 1 / k0 - 1 / n0)
    z = _z_crit(alpha)
    return rr - 1.0, ConfInt(rr * math.exp(-z * se_log) - 1.0, rr * math.exp(z * se_log) - 1.0)


def lift_estimate(k1: int, n1: int, k0: int, n0: int, alpha: float = 0.05) -> LiftEstimate:
    """Absolute lift (Newcombe CI) plus relative lift (Katz CI) in one object."""
    abs_lift = k1 / n1 - k0 / n0
    rel = relative_lift_ci(k1, n1, k0, n0, alpha)
    if rel is None:
        return LiftEstimate(abs_lift, newcombe_ci(k1, n1, k0, n0, alpha), None, None)
    rel_lift, rel_ci = rel
    return LiftEstimate(abs_lift, newcombe_ci(k1, n1, k0, n0, alpha), rel_lift, rel_ci)


def chi_square_karm(clicks: list[int], impressions: list[int]) -> tuple[float, float]:
    """Omnibus chi-square test that all k arms share one CTR.

    Returns (statistic, p_value) from the 2 x k contingency table
    [clicks; non-clicks]. Requires at least two arms.
    """
    if len(clicks) != len(impressions) or len(clicks) < 2:
        raise ValueError("need matching clicks/impressions for at least 2 arms")
    for k, n in zip(clicks, impressions, strict=True):
        _validate_counts(k, n)
    if sum(clicks) == 0 or sum(clicks) == sum(impressions):
        return 0.0, 1.0
    table = [clicks, [n - k for k, n in zip(clicks, impressions, strict=True)]]
    res = stats.chi2_contingency(table, correction=False)
    return float(res.statistic), float(res.pvalue)
