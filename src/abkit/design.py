"""Design tools: power, sample size, and MDE for two-proportion tests.

Analytic normal-approximation formulas (Fleiss-style, unpooled variance under
the alternative, pooled under the null), each simulation-checked in
``tests/test_design.py``.
"""

from __future__ import annotations

import math

from scipy import optimize, stats


def _validate_rate(p: float, name: str) -> None:
    if not 0.0 < p < 1.0:
        raise ValueError(f"{name} must be in (0, 1), got {p}")


def power_two_prop(p0: float, p1: float, n_per_arm: int, alpha: float = 0.05) -> float:
    """Power of a two-sided pooled two-proportion z-test with n per arm."""
    _validate_rate(p0, "p0")
    _validate_rate(p1, "p1")
    if n_per_arm <= 0:
        raise ValueError("n_per_arm must be positive")
    if p0 == p1:
        return alpha  # power at the null equals the type-I error rate
    delta = abs(p1 - p0)
    z_a = float(stats.norm.ppf(1 - alpha / 2))
    p_bar = (p0 + p1) / 2
    se0 = math.sqrt(2 * p_bar * (1 - p_bar) / n_per_arm)  # H0 (pooled) scale
    se1 = math.sqrt((p0 * (1 - p0) + p1 * (1 - p1)) / n_per_arm)  # H1 scale
    upper = float(stats.norm.cdf((delta - z_a * se0) / se1))
    lower = float(stats.norm.cdf((-delta - z_a * se0) / se1))  # wrong-direction rejection
    return min(1.0, upper + lower)


def sample_size_two_prop(
    p0: float, p1: float, alpha: float = 0.05, power: float = 0.80
) -> int:
    """Smallest n per arm giving at least `power` for detecting p0 vs p1.

    Closed-form seed, then verified/adjusted against :func:`power_two_prop`
    so the returned n actually achieves the requested power under the same
    formula the readout uses.
    """
    _validate_rate(p0, "p0")
    _validate_rate(p1, "p1")
    if p0 == p1:
        raise ValueError("p0 and p1 must differ")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be in (0, 1)")
    delta = abs(p1 - p0)
    z_a = float(stats.norm.ppf(1 - alpha / 2))
    z_b = float(stats.norm.ppf(power))
    p_bar = (p0 + p1) / 2
    n = (
        z_a * math.sqrt(2 * p_bar * (1 - p_bar))
        + z_b * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))
    ) ** 2 / delta**2
    n_int = max(2, math.ceil(n))
    while power_two_prop(p0, p1, n_int, alpha) < power:
        n_int = math.ceil(n_int * 1.02) + 1
    while n_int > 2 and power_two_prop(p0, p1, n_int - 1, alpha) >= power:
        n_int -= 1
    return n_int


def mde_two_prop(
    p0: float, n_per_arm: int, alpha: float = 0.05, power: float = 0.80
) -> float:
    """Minimum detectable absolute lift (upward) at the given n per arm.

    Solved numerically so it is exactly consistent with :func:`power_two_prop`.
    Returns the absolute difference p1 - p0.
    """
    _validate_rate(p0, "p0")
    if n_per_arm <= 0:
        raise ValueError("n_per_arm must be positive")

    def gap(delta: float) -> float:
        return power_two_prop(p0, p0 + delta, n_per_arm, alpha) - power

    hi = 1.0 - p0 - 1e-9
    if gap(hi) < 0:
        raise ValueError(
            f"even the maximum possible lift is undetectable at power={power} with n={n_per_arm}"
        )
    return float(optimize.brentq(gap, 1e-12, hi, xtol=1e-12))
