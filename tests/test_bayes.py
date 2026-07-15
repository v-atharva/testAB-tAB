"""Validate the Bayesian readout: prior fitting, P(best), expected loss."""

import numpy as np
import pytest

from abkit import bayes

RNG = np.random.default_rng(23)


class TestPriorFit:
    def test_recovers_known_beta_prior(self) -> None:
        """Simulate arms whose true CTRs come from a known Beta; MLE should recover it."""
        true = bayes.BetaPrior(a=30.0, b=2000.0)  # mean ~1.5%, Upworthy-like
        n_arms = 3000
        ps = RNG.beta(true.a, true.b, size=n_arms)
        ns = RNG.integers(2000, 6000, size=n_arms)
        ks = RNG.binomial(ns, ps)
        fit = bayes.fit_beta_prior([int(k) for k in ks], [int(n) for n in ns])
        assert fit.mean == pytest.approx(true.mean, rel=0.03)
        # concentration is harder to pin; accept the right order of magnitude
        assert fit.a + fit.b == pytest.approx(true.a + true.b, rel=0.35)

    def test_needs_enough_arms(self) -> None:
        with pytest.raises(ValueError):
            bayes.fit_beta_prior([1, 2], [100, 100])


class TestProbBest:
    def test_symmetric_arms_split_evenly(self) -> None:
        prior = bayes.BetaPrior(30, 2000)
        out = bayes.bayes_readout([50, 50, 50], [3000, 3000, 3000], prior, seed=1)
        for p in out.p_best:
            assert p == pytest.approx(1 / 3, abs=0.01)
        assert sum(out.p_best) == pytest.approx(1.0, abs=1e-9)

    def test_exact_two_arm_matches_monte_carlo(self) -> None:
        prior = bayes.BetaPrior(30, 2000)
        exact = bayes.prob_beats_baseline(70, 3000, 50, 3000, prior)
        mc = bayes.bayes_readout([50, 70], [3000, 3000], prior, mc_draws=500_000, seed=2)
        assert mc.p_best[1] == pytest.approx(exact, abs=0.005)

    def test_calibration_against_truth(self) -> None:
        """P(best) is calibrated: among sims where P(best of arm1) ~ 0.8,
        arm1 should truly be best ~80% of the time."""
        prior = bayes.BetaPrior(30, 2000)
        n, reps = 3000, 3000
        hits = tot = 0
        for _ in range(reps):
            p_true = RNG.beta(prior.a, prior.b, size=2)
            ks = RNG.binomial(n, p_true)
            out = bayes.bayes_readout([int(ks[0]), int(ks[1])], [n, n], prior,
                                      mc_draws=20_000, seed=int(ks.sum()))
            if 0.75 <= out.p_best[1] <= 0.85:
                tot += 1
                hits += bool(p_true[1] > p_true[0])
        assert tot > 100  # the bucket is populated
        assert hits / tot == pytest.approx(0.80, abs=0.06)


class TestExpectedLoss:
    def test_dominant_arm_has_near_zero_loss(self) -> None:
        prior = bayes.BetaPrior(30, 2000)
        out = bayes.bayes_readout([200, 50], [3000, 3000], prior, seed=3)
        assert out.expected_loss[0] < 1e-5   # the clear winner
        assert out.expected_loss[1] > 0.001  # picking the loser costs real CTR

    def test_loss_is_nonnegative_and_winner_minimizes_it(self) -> None:
        prior = bayes.BetaPrior(30, 2000)
        out = bayes.bayes_readout([55, 60, 45], [3000, 3100, 2900], prior, seed=4)
        assert all(loss >= 0 for loss in out.expected_loss)
        assert int(np.argmin(out.expected_loss)) == int(np.argmax(out.p_best))
