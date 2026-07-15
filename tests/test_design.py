"""Validate power/sample-size/MDE against simulation and internal consistency."""

import numpy as np
import pytest

from abkit import design, freq

RNG = np.random.default_rng(7)


def _simulated_power(p0: float, p1: float, n: int, alpha: float, reps: int = 20_000) -> float:
    k1 = RNG.binomial(n, p1, size=reps)
    k0 = RNG.binomial(n, p0, size=reps)
    rejections = sum(
        freq.two_prop_ztest(int(a), n, int(b), n).p_value < alpha
        for a, b in zip(k1, k0, strict=True)
    )
    return rejections / reps


class TestPower:
    @pytest.mark.parametrize(
        "p0,p1,n",
        [
            (0.015, 0.020, 3000),   # corpus-typical: median arm size, healthy lift
            (0.015, 0.0165, 3000),  # corpus-typical: small lift (should be low power)
            (0.10, 0.12, 2000),
        ],
    )
    def test_analytic_power_matches_simulation(self, p0: float, p1: float, n: int) -> None:
        analytic = design.power_two_prop(p0, p1, n, alpha=0.05)
        simulated = _simulated_power(p0, p1, n, alpha=0.05)
        assert analytic == pytest.approx(simulated, abs=0.015)

    def test_power_at_null_equals_alpha(self) -> None:
        assert design.power_two_prop(0.015, 0.015, 3000, alpha=0.05) == 0.05

    def test_power_monotone_in_n_and_effect(self) -> None:
        assert design.power_two_prop(0.015, 0.02, 6000) > design.power_two_prop(0.015, 0.02, 3000)
        assert design.power_two_prop(0.015, 0.02, 3000) > design.power_two_prop(0.015, 0.017, 3000)


class TestSampleSizeAndMde:
    def test_sample_size_achieves_requested_power(self) -> None:
        n = design.sample_size_two_prop(0.015, 0.018, alpha=0.05, power=0.80)
        assert design.power_two_prop(0.015, 0.018, n) >= 0.80
        assert design.power_two_prop(0.015, 0.018, n - 1) < 0.80  # minimal

    def test_sample_size_matches_simulation(self) -> None:
        n = design.sample_size_two_prop(0.015, 0.020, power=0.80)
        assert _simulated_power(0.015, 0.020, n, alpha=0.05) == pytest.approx(0.80, abs=0.02)

    def test_mde_round_trips_with_power(self) -> None:
        mde = design.mde_two_prop(0.015, 3122, alpha=0.05, power=0.80)  # median Upworthy arm
        assert design.power_two_prop(0.015, 0.015 + mde, 3122) == pytest.approx(0.80, abs=1e-6)

    def test_median_upworthy_arm_cannot_detect_small_lifts(self) -> None:
        """The corpus story in one assertion: the median test needs a ~30%+
        relative lift to be adequately powered."""
        mde = design.mde_two_prop(0.015, 3122, power=0.80)
        assert mde / 0.015 > 0.30

    def test_validation(self) -> None:
        with pytest.raises(ValueError):
            design.power_two_prop(0.0, 0.5, 100)
        with pytest.raises(ValueError):
            design.sample_size_two_prop(0.5, 0.5)
        with pytest.raises(ValueError):
            design.mde_two_prop(0.015, 3, power=0.999)
