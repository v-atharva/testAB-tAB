"""Validate SRM test and quality gates."""

import numpy as np
import pytest

from abkit import health

RNG = np.random.default_rng(63)


class TestSrm:
    def test_type_i_rate_matches_alpha(self) -> None:
        """Uniform 4-arm allocation should fail SRM ~ alpha of the time."""
        reps, alpha, arms, total = 20_000, 0.001, 4, 12_000
        fails = 0
        for _ in range(reps):
            ns = RNG.multinomial(total, [1 / arms] * arms)
            fails += health.srm_test([int(x) for x in ns], alpha=alpha).failed
        assert fails / reps == pytest.approx(alpha, abs=0.001)

    def test_detects_real_mismatch(self) -> None:
        """A 52/48 split with a whole test's traffic (~40k assignments, the
        scale where SRM matters) is caught essentially always at alpha=1e-3."""
        detected = 0
        for _ in range(200):
            ns = RNG.multinomial(40_000, [0.52, 0.48])
            detected += health.srm_test([int(x) for x in ns], alpha=0.001).failed
        assert detected / 200 > 0.95

    def test_custom_expected_shares(self) -> None:
        res = health.srm_test([9000, 1000], expected_shares=[0.9, 0.1])
        assert not res.failed
        res = health.srm_test([9000, 1000], expected_shares=[0.5, 0.5])
        assert res.failed

    def test_validation(self) -> None:
        with pytest.raises(ValueError):
            health.srm_test([100])
        with pytest.raises(ValueError):
            health.srm_test([100, 100], expected_shares=[0.6, 0.6])


class TestQualityReport:
    def test_flags_and_gates(self) -> None:
        rep = health.quality_report(
            clicks=[0, 50, 3],
            impressions=[80, 3000, 3000],
            stimuli=["same headline", "same headline", "different"],
            min_impressions_per_arm=100,
        )
        assert rep.zero_click_arms == [0]
        assert rep.below_min_impressions == [0]
        assert rep.duplicate_stimuli_groups == [[0, 1]]
        assert rep.gated

    def test_healthy_experiment_passes(self) -> None:
        rep = health.quality_report([50, 60], [3000, 3100])
        assert not rep.gated
        assert rep.reasons == []
