"""Sequential (anytime-valid) inference for two-proportion streams.

mSPRT with a normal mixture (Johari, Koomen, Pekelis & Walsh 2017 style):
the test statistic may be monitored continuously ("peeked") without inflating
the type-I error. Produces always-valid p-values and confidence sequences.
A classic O'Brien-Fleming group-sequential boundary is provided for contrast,
and a conditional-permutation replay reconstructs a plausible within-test
trajectory from the archive's final counts (no event-level data exists).

Model: at look t the estimated lift theta_hat_t = p1_hat - p0_hat is treated
as Normal(theta, V_t) with V_t the pooled-variance estimate. The mixture
likelihood ratio against H0: theta = 0 with prior N(0, phi) is

    Lambda_t = sqrt(V_t / (V_t + phi)) * exp( phi * theta_hat_t^2 / (2 V_t (V_t + phi)) )

which is (asymptotically) a nonnegative martingale under H0, so
p_t = min_{s<=t} 1 / Lambda_s is an always-valid p-value (Ville's inequality).
Validation in tests/test_sequential.py: empirical P(ever reject | H0) <= alpha
under continuous monitoring, versus the naive repeated z-test which inflates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import stats


@dataclass(frozen=True)
class SequentialTrace:
    """Anytime-valid readout at each look of a two-arm stream (arrays align with looks)."""

    theta_hat: NDArray[np.float64]  # estimated lift p1 - p0 at each look
    always_valid_p: NDArray[np.float64]
    cs_radius: NDArray[np.float64]  # confidence-sequence half-width around theta_hat
    first_rejection: int | None  # earliest look index with p < alpha, else None


def msprt_two_prop(
    k1: NDArray[np.int64] | list[int],
    n1: NDArray[np.int64] | list[int],
    k0: NDArray[np.int64] | list[int],
    n0: NDArray[np.int64] | list[int],
    phi: float,
    alpha: float = 0.05,
) -> SequentialTrace:
    """mSPRT over cumulative counts (k = clicks, n = impressions) per look.

    Inputs are CUMULATIVE and non-decreasing. `phi` is the mixture variance on
    the absolute lift scale (config: sequential.mixture_phi).
    """
    k1a = np.asarray(k1, dtype=np.float64)
    n1a = np.asarray(n1, dtype=np.float64)
    k0a = np.asarray(k0, dtype=np.float64)
    n0a = np.asarray(n0, dtype=np.float64)
    if not (k1a.shape == n1a.shape == k0a.shape == n0a.shape) or k1a.ndim != 1:
        raise ValueError("all four count arrays must be 1-D and the same length")
    if phi <= 0:
        raise ValueError("phi must be positive")
    for arr in (k1a, n1a, k0a, n0a):
        if np.any(np.diff(arr) < 0):
            raise ValueError("counts must be cumulative (non-decreasing)")

    with np.errstate(divide="ignore", invalid="ignore"):
        p1 = np.where(n1a > 0, k1a / n1a, 0.0)
        p0 = np.where(n0a > 0, k0a / n0a, 0.0)
        pooled = np.where(n1a + n0a > 0, (k1a + k0a) / (n1a + n0a), 0.0)
        v = pooled * (1 - pooled) * (1 / np.maximum(n1a, 1) + 1 / np.maximum(n0a, 1))
    theta = p1 - p0

    valid = (n1a > 0) & (n0a > 0) & (v > 0)
    log_lambda = np.zeros_like(theta)
    log_lambda[valid] = 0.5 * np.log(v[valid] / (v[valid] + phi)) + (
        phi * theta[valid] ** 2 / (2 * v[valid] * (v[valid] + phi))
    )
    # always-valid p: running minimum of 1/Lambda, capped at 1
    p_inst = np.minimum(1.0, np.exp(-log_lambda))
    p_av = np.minimum.accumulate(p_inst)

    radius = np.full_like(theta, np.inf)
    radius[valid] = np.sqrt(
        (2 * v[valid] * (v[valid] + phi) / phi)
        * (math.log(1 / alpha) + 0.5 * np.log((v[valid] + phi) / v[valid]))
    )

    below = np.nonzero(p_av < alpha)[0]
    first = int(below[0]) if below.size else None
    return SequentialTrace(
        theta_hat=theta, always_valid_p=p_av, cs_radius=radius, first_rejection=first
    )


def naive_peeking_rejections(
    k1: NDArray[np.int64] | list[int],
    n1: NDArray[np.int64] | list[int],
    k0: NDArray[np.int64] | list[int],
    n0: NDArray[np.int64] | list[int],
    alpha: float = 0.05,
) -> int | None:
    """First look where a NAIVE repeated two-proportion z-test rejects.

    This is the malpractice being measured, not a method on offer: stopping at
    the first p < alpha over many looks inflates the false-positive rate far
    above alpha.
    """
    k1a = np.asarray(k1, dtype=np.float64)
    n1a = np.asarray(n1, dtype=np.float64)
    k0a = np.asarray(k0, dtype=np.float64)
    n0a = np.asarray(n0, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        pooled = np.where(n1a + n0a > 0, (k1a + k0a) / (n1a + n0a), 0.0)
        v = pooled * (1 - pooled) * (1 / np.maximum(n1a, 1) + 1 / np.maximum(n0a, 1))
        z = np.where(v > 0, (k1a / np.maximum(n1a, 1) - k0a / np.maximum(n0a, 1)) / np.sqrt(v), 0.0)
    p = 2 * stats.norm.sf(np.abs(z))
    below = np.nonzero((p < alpha) & (n1a > 0) & (n0a > 0))[0]
    return int(below[0]) if below.size else None


def obrien_fleming_boundaries(
    n_looks: int,
    alpha: float = 0.05,
    n_sims: int = 200_000,
    seed: int = 0,
) -> NDArray[np.float64]:
    """Two-sided O'Brien-Fleming z-boundaries at equally spaced looks.

    The OBF shape is b_k = C / sqrt(t_k) with t_k = k / K; the constant C is
    calibrated by Monte Carlo over Brownian-motion sample paths so that the
    overall crossing probability under H0 equals alpha. Simulation-calibrated
    rather than numerically integrated on purpose: the calibration IS the
    correctness proof, and it is checked against published constants in tests
    (K=1 -> 1.960, K=5 -> ~2.04 at alpha=0.05).
    """
    if n_looks < 1:
        raise ValueError("n_looks must be >= 1")
    if n_looks == 1:
        return np.array([float(stats.norm.ppf(1 - alpha / 2))])
    rng = np.random.default_rng(seed)
    t = np.arange(1, n_looks + 1) / n_looks
    increments = rng.normal(0.0, np.sqrt(1.0 / n_looks), size=(n_sims, n_looks))
    w = np.cumsum(increments, axis=1)
    z = w / np.sqrt(t)  # z-statistics at each look under H0
    # For a candidate C, path rejects iff max_k |z_k| * sqrt(t_k) >= C
    m = np.max(np.abs(z) * np.sqrt(t), axis=1)
    c = float(np.quantile(m, 1 - alpha))
    return c / np.sqrt(t)


def conditional_permutation_replay(
    clicks: int,
    impressions: int,
    n_looks: int,
    rng: np.random.Generator,
) -> NDArray[np.int64]:
    """Cumulative clicks of one arm at `n_looks` evenly spaced sample sizes.

    Exact conditional replay: the arm's `impressions` Bernoulli outcomes (of
    which exactly `clicks` are successes) are randomly permuted and streamed.
    This reconstructs a trajectory consistent with the observed totals —
    the archive has no event-level timestamps, so any within-test path is a
    reconstruction and the dashboard labels it as such.
    """
    if not 0 <= clicks <= impressions:
        raise ValueError("need 0 <= clicks <= impressions")
    outcomes = np.zeros(impressions, dtype=np.int64)
    outcomes[:clicks] = 1
    rng.shuffle(outcomes)
    cum = np.concatenate([[0], np.cumsum(outcomes)])
    ns = np.linspace(0, impressions, n_looks + 1)[1:].astype(np.int64)
    return cum[ns]


def replay_looks(impressions: int, n_looks: int) -> NDArray[np.int64]:
    """The cumulative sample sizes used by :func:`conditional_permutation_replay`."""
    return np.linspace(0, impressions, n_looks + 1)[1:].astype(np.int64)
