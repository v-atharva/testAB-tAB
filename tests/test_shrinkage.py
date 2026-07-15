"""Validate empirical-Bayes shrinkage and winner's-curse machinery by simulation.

The claims under test are the project's central ones:
1. the marginal MLE recovers a known (mu, tau^2);
2. shrunk estimates beat naive ones in MSE and their intervals are calibrated;
3. the observed lift of a SELECTED winner is biased upward, by the amount
   expected_winner_exaggeration predicts, and shrinkage removes most of it.
"""

import math

import numpy as np
import pytest

from abkit import shrinkage

RNG = np.random.default_rng(31)

# Upworthy-like scale: true log-odds lifts centered ~0 with sd ~0.1,
# noise se ~0.19 (two arms of ~3000 impressions at 1.5% CTR).
TRUE = shrinkage.NormalPrior(mu=0.01, tau2=0.010)
SE2_RANGE = (0.02, 0.08)


def _simulate_corpus(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    theta = RNG.normal(TRUE.mu, TRUE.tau, size=n)
    se2 = RNG.uniform(*SE2_RANGE, size=n)
    theta_hat = theta + RNG.normal(0, np.sqrt(se2))
    return theta, theta_hat, se2


class TestPriorFit:
    def test_recovers_known_prior(self) -> None:
        _, theta_hat, se2 = _simulate_corpus(20_000)
        fit = shrinkage.fit_normal_prior(theta_hat, se2)
        assert fit.mu == pytest.approx(TRUE.mu, abs=0.005)
        assert fit.tau2 == pytest.approx(TRUE.tau2, rel=0.10)

    def test_log_odds_lift_matches_hand_computation(self) -> None:
        res = shrinkage.log_odds_lift(70, 3000, 50, 3000)
        assert res is not None
        theta, se2 = res
        assert theta == pytest.approx(
            math.log(70 / 2930) - math.log(50 / 2950), abs=1e-12
        )
        assert se2 == pytest.approx(1 / 70 + 1 / 2930 + 1 / 50 + 1 / 2950, abs=1e-12)

    def test_zero_cells_are_not_shrinkable(self) -> None:
        assert shrinkage.log_odds_lift(0, 100, 5, 100) is None
        assert shrinkage.log_odds_lift(5, 100, 100, 100) is None


class TestShrinkage:
    def test_shrunk_beats_naive_mse_and_is_calibrated(self) -> None:
        theta, theta_hat, se2 = _simulate_corpus(20_000)
        fit = shrinkage.fit_normal_prior(theta_hat, se2)
        post = [shrinkage.shrink(t, v, fit) for t, v in zip(theta_hat, se2, strict=True)]
        shrunk = np.array([p.post_mean for p in post])
        mse_naive = float(np.mean((theta_hat - theta) ** 2))
        mse_shrunk = float(np.mean((shrunk - theta) ** 2))
        assert mse_shrunk < 0.5 * mse_naive  # heavy noise -> shrinkage wins big

        covered = sum(
            p.interval(0.05)[0] <= t <= p.interval(0.05)[1]
            for p, t in zip(post, theta, strict=True)
        )
        assert covered / len(theta) == pytest.approx(0.95, abs=0.01)

    def test_shrinks_toward_prior_mean_proportionally_to_noise(self) -> None:
        prior = shrinkage.NormalPrior(mu=0.0, tau2=0.01)
        low_noise = shrinkage.shrink(0.5, 0.001, prior).post_mean
        high_noise = shrinkage.shrink(0.5, 0.1, prior).post_mean
        assert high_noise < low_noise < 0.5
        assert high_noise < 0.1  # nearly all the way back to the prior


class TestWinnersCurse:
    def test_selected_winner_is_exaggerated_and_shrinkage_fixes_it(self) -> None:
        """4-arm tests: the apparent winner's naive lift overshoots its own true
        lift; the shrunk estimate does not (on average)."""
        n_tests, k_arms = 4000, 3
        se2 = np.full((n_tests, k_arms), 0.05)  # underpowered, Upworthy-like
        theta = RNG.normal(TRUE.mu, TRUE.tau, size=(n_tests, k_arms))
        theta_hat = theta + RNG.normal(0, np.sqrt(se2))
        winner = theta_hat.argmax(axis=1)
        rows = np.arange(n_tests)
        naive_bias = float(np.mean(theta_hat[rows, winner] - theta[rows, winner]))
        assert naive_bias > 0.05  # large, systematic exaggeration

        fit = shrinkage.fit_normal_prior(theta_hat.ravel(), se2.ravel())
        shrunk = np.array(
            [shrinkage.shrink(theta_hat[i, winner[i]], se2[i, winner[i]], fit).post_mean
             for i in range(n_tests)]
        )
        shrunk_bias = float(np.mean(shrunk - theta[rows, winner]))
        assert abs(shrunk_bias) < 0.25 * naive_bias

    def test_exaggeration_factor_matches_direct_simulation(self) -> None:
        se2 = [0.05, 0.05, 0.05]
        factor = shrinkage.expected_winner_exaggeration(se2, TRUE, n_sims=200_000, seed=5)
        assert factor > 1.5  # underpowered tests exaggerate a lot

        # and it shrinks toward 1 as power rises
        precise = shrinkage.expected_winner_exaggeration(
            [0.0005, 0.0005, 0.0005], TRUE, n_sims=200_000, seed=6
        )
        assert 1.0 < precise < factor
