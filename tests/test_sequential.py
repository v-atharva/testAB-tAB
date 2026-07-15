"""Validate anytime-valid inference — the module with the heaviest proof burden.

Headline claims:
1. mSPRT monitored at EVERY look keeps P(ever reject | H0) <= alpha;
2. the naive repeated z-test does not (it inflates severely);
3. the confidence sequence covers the true lift at ALL looks simultaneously
   with >= 1 - alpha probability;
4. O'Brien-Fleming calibration reproduces published constants.
"""

import numpy as np
import pytest

from abkit import sequential

PHI = 1.0e-5  # config default: mixture variance ~ E[theta^2] under the corpus prior
CTR = 0.015
N_FINAL = 6000  # per arm
N_LOOKS = 50


def _simulate_stream(
    rng: np.random.Generator, p1: float, p0: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    looks = sequential.replay_looks(N_FINAL, N_LOOKS)
    x1 = rng.binomial(1, p1, size=N_FINAL)
    x0 = rng.binomial(1, p0, size=N_FINAL)
    return np.cumsum(x1)[looks - 1], looks, np.cumsum(x0)[looks - 1], looks


class TestAnytimeValidity:
    def test_msprt_controls_type_i_under_continuous_monitoring(self) -> None:
        rng = np.random.default_rng(101)
        reps, alpha = 2000, 0.05
        false_stops = 0
        for _ in range(reps):
            k1, n1, k0, n0 = _simulate_stream(rng, CTR, CTR)
            trace = sequential.msprt_two_prop(k1, n1, k0, n0, phi=PHI, alpha=alpha)
            false_stops += trace.first_rejection is not None
        # Ville's inequality guarantees <= alpha; mixture tests run conservative.
        assert false_stops / reps <= alpha + 0.01

    def test_naive_peeking_inflates_type_i(self) -> None:
        rng = np.random.default_rng(102)
        reps, alpha = 2000, 0.05
        false_stops = 0
        for _ in range(reps):
            k1, n1, k0, n0 = _simulate_stream(rng, CTR, CTR)
            false_stops += sequential.naive_peeking_rejections(k1, n1, k0, n0, alpha) is not None
        # With 50 looks, stop-at-first-p<0.05 fires on far more than 5% of nulls.
        assert false_stops / reps > 2.5 * alpha

    def test_msprt_has_power_under_real_effects(self) -> None:
        """Anytime validity costs power at a fixed horizon; at a horizon where
        the fixed-n z-test would sit at z~5.5, mSPRT must still detect nearly
        always. (At the median Upworthy arm size it usually cannot — that IS
        the corpus finding, quantified in the meta-analysis.)"""
        rng = np.random.default_rng(103)
        reps, n_final = 400, 20_000
        looks = sequential.replay_looks(n_final, N_LOOKS)
        stops = 0
        for _ in range(reps):
            x1 = rng.binomial(1, CTR * 1.5, size=n_final)  # +50% lift
            x0 = rng.binomial(1, CTR, size=n_final)
            trace = sequential.msprt_two_prop(
                np.cumsum(x1)[looks - 1], looks, np.cumsum(x0)[looks - 1], looks, phi=PHI
            )
            stops += trace.first_rejection is not None
        assert stops / reps > 0.9

    def test_confidence_sequence_uniform_coverage(self) -> None:
        """P(theta in CS at EVERY look) >= 1 - alpha — the anytime guarantee."""
        rng = np.random.default_rng(104)
        reps, truth = 2000, CTR * 0.2
        always_covered = 0
        for _ in range(reps):
            k1, n1, k0, n0 = _simulate_stream(rng, CTR + truth, CTR)
            trace = sequential.msprt_two_prop(k1, n1, k0, n0, phi=PHI)
            inside = np.abs(trace.theta_hat - truth) <= trace.cs_radius
            always_covered += bool(inside.all())
        assert always_covered / reps >= 0.95 - 0.01


class TestObrienFleming:
    def test_single_look_reduces_to_fixed_test(self) -> None:
        b = sequential.obrien_fleming_boundaries(1, alpha=0.05)
        assert b[0] == pytest.approx(1.960, abs=0.001)

    def test_five_look_constant_matches_literature(self) -> None:
        b = sequential.obrien_fleming_boundaries(5, alpha=0.05, n_sims=400_000, seed=1)
        # Published OBF final boundary for K=5, two-sided alpha=0.05: ~2.04
        assert b[-1] == pytest.approx(2.04, abs=0.03)
        # shape: early looks are much stricter
        assert b[0] == pytest.approx(b[-1] * np.sqrt(5), rel=1e-9)

    def test_calibration_holds_empirically(self) -> None:
        """Fresh H0 paths crossed by the calibrated boundary ~ alpha of the time."""
        k, alpha = 10, 0.05
        b = sequential.obrien_fleming_boundaries(k, alpha=alpha, n_sims=400_000, seed=2)
        rng = np.random.default_rng(999)
        t = np.arange(1, k + 1) / k
        w = np.cumsum(rng.normal(0, np.sqrt(1 / k), size=(100_000, k)), axis=1)
        z = w / np.sqrt(t)
        crossed = (np.abs(z) >= b).any(axis=1).mean()
        assert crossed == pytest.approx(alpha, abs=0.005)


class TestReplay:
    def test_replay_conserves_totals_and_is_deterministic(self) -> None:
        rng1 = np.random.default_rng(55)
        rng2 = np.random.default_rng(55)
        a = sequential.conditional_permutation_replay(47, 3122, 30, rng1)
        b = sequential.conditional_permutation_replay(47, 3122, 30, rng2)
        np.testing.assert_array_equal(a, b)
        assert a[-1] == 47
        assert (np.diff(a) >= 0).all()
        assert len(a) == 30

    def test_replay_edge_cases(self) -> None:
        rng = np.random.default_rng(56)
        zero = sequential.conditional_permutation_replay(0, 500, 10, rng)
        assert zero[-1] == 0
        full = sequential.conditional_permutation_replay(500, 500, 10, rng)
        assert full[-1] == 500
        with pytest.raises(ValueError):
            sequential.conditional_permutation_replay(10, 5, 3, rng)

    def test_msprt_input_validation(self) -> None:
        with pytest.raises(ValueError):
            sequential.msprt_two_prop([5, 3], [100, 200], [4, 8], [100, 200], phi=PHI)
        with pytest.raises(ValueError):
            sequential.msprt_two_prop([1], [10], [1], [10], phi=-1.0)
