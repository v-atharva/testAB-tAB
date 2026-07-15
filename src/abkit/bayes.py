"""Bayesian readout: Beta-Binomial posteriors, P(best), expected loss.

The prior is a single Beta(a, b) on CTR, fit once on the exploratory corpus
(see analysis/fit_priors.py) — an empirical prior, not a subjective one.

When each framing helps a decision-maker
----------------------------------------
* Frequentist CIs + corrected p-values answer "could this be noise?" and are
  the right gate for one-shot ship/no-ship claims with error guarantees.
* P(best) and expected loss answer "if I must pick an arm today, how bad can
  my pick be?" — useful when a decision is forced before significance is
  reachable, as in Upworthy's fast editorial cycle. Expected loss near zero
  is a principled reason to ship early; P(best)=0.9 alone is not a
  significance claim and the readout never presents it as one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import integrate, optimize, stats


@dataclass(frozen=True)
class BetaPrior:
    a: float
    b: float

    @property
    def mean(self) -> float:
        return self.a / (self.a + self.b)


@dataclass(frozen=True)
class BayesReadout:
    """Per-arm posterior summary for a k-arm test (same arm order as input)."""

    post_mean: list[float]
    p_best: list[float]
    expected_loss: list[float]  # E[best CTR - this arm's CTR] under the posterior


def fit_beta_prior(clicks: list[int], impressions: list[int]) -> BetaPrior:
    """MLE of a Beta(a, b) prior from many arms' (clicks, impressions).

    Maximizes the Beta-Binomial marginal likelihood — the standard
    empirical-Bayes fit for over-dispersed binomial rates.
    """
    k = np.asarray(clicks, dtype=np.int64)
    n = np.asarray(impressions, dtype=np.int64)
    if k.size < 10:
        raise ValueError("need at least 10 arms to fit a corpus prior")

    def neg_loglik(log_params: np.ndarray) -> float:
        a, b = np.exp(log_params)
        return -float(np.sum(stats.betabinom.logpmf(k, n, a, b)))

    p_hat = float(k.sum() / n.sum())
    x0 = np.log([p_hat * 100, (1 - p_hat) * 100])
    res = optimize.minimize(neg_loglik, x0, method="Nelder-Mead", options={"xatol": 1e-6})
    if not res.success:
        raise RuntimeError(f"beta prior fit did not converge: {res.message}")
    a, b = np.exp(res.x)
    return BetaPrior(float(a), float(b))


def prob_beats_baseline(
    k1: int, n1: int, k0: int, n0: int, prior: BetaPrior
) -> float:
    """Exact P(p1 > p0 | data) for two arms via numerical integration."""
    a1, b1 = prior.a + k1, prior.b + n1 - k1
    a0, b0 = prior.a + k0, prior.b + n0 - k0

    def integrand(x: float) -> float:
        return float(stats.beta.pdf(x, a1, b1) * stats.beta.cdf(x, a0, b0))

    val, _ = integrate.quad(integrand, 0.0, 1.0, limit=200)
    return float(min(1.0, max(0.0, val)))


def bayes_readout(
    clicks: list[int],
    impressions: list[int],
    prior: BetaPrior,
    mc_draws: int = 200_000,
    seed: int = 0,
) -> BayesReadout:
    """P(best) and expected loss for each arm of a k-arm test, by Monte Carlo.

    A single draw matrix is shared by both quantities, so they are mutually
    consistent. With 2e5 draws the MC standard error on P(best) is < 0.2 pp.
    """
    k = np.asarray(clicks, dtype=np.int64)
    n = np.asarray(impressions, dtype=np.int64)
    if k.size < 2:
        raise ValueError("need at least 2 arms")
    rng = np.random.default_rng(seed)
    draws = rng.beta(prior.a + k, prior.b + (n - k), size=(mc_draws, k.size))
    best = draws.max(axis=1)
    p_best = np.bincount(draws.argmax(axis=1), minlength=k.size) / mc_draws
    exp_loss = (best[:, None] - draws).mean(axis=0)
    post_mean = (prior.a + k) / (prior.a + prior.b + n)
    return BayesReadout(
        post_mean=[float(x) for x in post_mean],
        p_best=[float(x) for x in p_best],
        expected_loss=[float(x) for x in exp_loss],
    )
