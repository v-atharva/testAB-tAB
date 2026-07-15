"""Empirical-Bayes shrinkage of observed lifts, and winner's-curse tooling.

The centerpiece of this project. Model:

    theta_hat_i ~ Normal(theta_i, se_i^2)     (sampling noise, se known from counts)
    theta_i     ~ Normal(mu, tau^2)           (corpus prior on TRUE log-odds lifts)

where theta = logit(p_variant) - logit(p_baseline) is the log-odds lift of a
variant over its within-test baseline, and se^2 is the Woolf variance
1/k1 + 1/(n1-k1) + 1/k0 + 1/(n0-k0). (mu, tau^2) are fit by marginal MLE on
the exploratory corpus only. The posterior mean shrinks noisy lifts toward mu,
which corrects the winner's curse: the arm you noticed BECAUSE it looked best
is, in expectation, exaggerated, and more so when se is large (low power).

At Upworthy's ~1.5% CTRs the odds ratio and the relative CTR lift (risk
ratio) agree to within ~1% of themselves, so exp(theta)-1 is displayed as the
relative lift with that approximation documented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import optimize, stats


@dataclass(frozen=True)
class NormalPrior:
    """Corpus prior on true log-odds lifts."""

    mu: float
    tau2: float

    @property
    def tau(self) -> float:
        return math.sqrt(self.tau2)


@dataclass(frozen=True)
class ShrunkEstimate:
    """Posterior of a single true lift given its noisy observation."""

    post_mean: float
    post_var: float

    def interval(self, alpha: float = 0.05) -> tuple[float, float]:
        z = float(stats.norm.ppf(1 - alpha / 2))
        sd = math.sqrt(self.post_var)
        return self.post_mean - z * sd, self.post_mean + z * sd


def log_odds_lift(k1: int, n1: int, k0: int, n0: int) -> tuple[float, float] | None:
    """(theta_hat, se^2) of the log-odds lift; None when any cell is empty.

    Cells with k=0 or k=n make the log-odds infinite; those arms are excluded
    from prior fitting and reported as not-shrinkable in readouts.
    """
    if min(k1, n1 - k1, k0, n0 - k0) <= 0:
        return None
    theta = math.log(k1 / (n1 - k1)) - math.log(k0 / (n0 - k0))
    se2 = 1 / k1 + 1 / (n1 - k1) + 1 / k0 + 1 / (n0 - k0)
    return theta, se2


def fit_normal_prior(
    theta_hats: NDArray[np.float64] | list[float],
    se2s: NDArray[np.float64] | list[float],
) -> NormalPrior:
    """Marginal MLE of (mu, tau^2): theta_hat_i ~ N(mu, tau^2 + se_i^2)."""
    t = np.asarray(theta_hats, dtype=np.float64)
    v = np.asarray(se2s, dtype=np.float64)
    if t.size != v.size or t.size < 10:
        raise ValueError("need matching arrays with at least 10 lifts")
    if np.any(v <= 0):
        raise ValueError("sampling variances must be positive")

    def neg_loglik(params: NDArray[np.float64]) -> float:
        mu, log_tau2 = params
        total = v + np.exp(log_tau2)
        return float(0.5 * np.sum(np.log(total) + (t - mu) ** 2 / total))

    x0 = np.array([float(np.mean(t)), math.log(max(1e-6, float(np.var(t) - np.mean(v))))])
    res = optimize.minimize(neg_loglik, x0, method="Nelder-Mead", options={"xatol": 1e-8})
    if not res.success:
        raise RuntimeError(f"prior fit did not converge: {res.message}")
    mu, log_tau2 = res.x
    return NormalPrior(mu=float(mu), tau2=float(np.exp(log_tau2)))


def shrink(theta_hat: float, se2: float, prior: NormalPrior) -> ShrunkEstimate:
    """Normal-normal posterior of the true lift given one noisy observation."""
    if se2 <= 0:
        raise ValueError("se2 must be positive")
    w = prior.tau2 / (prior.tau2 + se2)  # weight on the data
    return ShrunkEstimate(
        post_mean=w * theta_hat + (1 - w) * prior.mu,
        post_var=w * se2,
    )


def expected_winner_exaggeration(
    se2s: NDArray[np.float64] | list[float],
    prior: NormalPrior,
    n_sims: int = 100_000,
    seed: int = 0,
) -> float:
    """E[observed winner lift] / E[true lift of that same winner] for a k-arm test.

    Simulates true lifts from the corpus prior, adds sampling noise with the
    test's actual standard errors, picks the apparent winner (as a naive
    readout would), and compares its observed lift to its own true lift.
    This is the selection-bias factor a naive readout suffers — a Monte Carlo
    version of Gelman & Carlin's Type-M error, priced with the corpus prior.
    Ratio is computed on lifts relative to the prior mean, guarding tiny
    denominators; returns NaN when the test has no comparisons.
    """
    v = np.asarray(se2s, dtype=np.float64)
    if v.size == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    true = rng.normal(prior.mu, prior.tau, size=(n_sims, v.size))
    obs = true + rng.normal(0.0, np.sqrt(v), size=(n_sims, v.size))
    winner = obs.argmax(axis=1)
    rows = np.arange(n_sims)
    obs_w = obs[rows, winner] - prior.mu
    true_w = true[rows, winner] - prior.mu
    denom = float(np.mean(true_w))
    if abs(denom) < 1e-12:
        return float("nan")
    return float(np.mean(obs_w) / denom)
