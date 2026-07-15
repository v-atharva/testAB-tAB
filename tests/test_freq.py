"""Validate frequentist readout against references and simulation."""

import numpy as np
import pytest
from scipy import stats
from statsmodels.stats.proportion import proportion_confint, proportions_ztest

from abkit import freq

RNG = np.random.default_rng(42)


class TestAgainstReferenceImplementations:
    @pytest.mark.parametrize("k,n", [(0, 50), (1, 100), (47, 3122), (150, 3052), (999, 1000)])
    def test_wilson_matches_statsmodels(self, k: int, n: int) -> None:
        ours = freq.wilson_ci(k, n, alpha=0.05)
        lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
        assert ours.lo == pytest.approx(lo, abs=1e-10)
        assert ours.hi == pytest.approx(hi, abs=1e-10)

    @pytest.mark.parametrize("k1,n1,k0,n0", [(150, 3052, 122, 3033), (10, 500, 25, 480)])
    def test_ztest_matches_statsmodels(self, k1: int, n1: int, k0: int, n0: int) -> None:
        ours = freq.two_prop_ztest(k1, n1, k0, n0)
        z_ref, p_ref = proportions_ztest([k1, k0], [n1, n0])
        assert ours.z == pytest.approx(z_ref, abs=1e-10)
        assert ours.p_value == pytest.approx(p_ref, abs=1e-10)

    def test_chi_square_matches_scipy(self) -> None:
        ks, ns = [150, 122, 110], [3052, 3033, 3092]
        stat, p = freq.chi_square_karm(ks, ns)
        table = [ks, [n - k for k, n in zip(ks, ns, strict=True)]]
        ref = stats.chi2_contingency(table, correction=False)
        assert stat == pytest.approx(ref.statistic)
        assert p == pytest.approx(ref.pvalue)


class TestBySimulation:
    def test_type_i_error_at_corpus_ctr(self) -> None:
        """Empirical type-I of the z-test ~ alpha at Upworthy-scale rates."""
        p, n, reps, alpha = 0.015, 3000, 20_000, 0.05
        k1 = RNG.binomial(n, p, size=reps)
        k0 = RNG.binomial(n, p, size=reps)
        rejections = sum(
            freq.two_prop_ztest(int(a), n, int(b), n).p_value < alpha
            for a, b in zip(k1, k0, strict=True)
        )
        assert rejections / reps == pytest.approx(alpha, abs=0.006)

    def test_wilson_coverage_at_corpus_ctr(self) -> None:
        p, n, reps = 0.015, 3000, 20_000
        ks = RNG.binomial(n, p, size=reps)
        covered = sum(freq.wilson_ci(int(k), n).lo <= p <= freq.wilson_ci(int(k), n).hi for k in ks)
        assert covered / reps == pytest.approx(0.95, abs=0.01)

    def test_newcombe_coverage_at_corpus_scale(self) -> None:
        """Nominal ~95% coverage of the difference CI in the modal Upworthy regime."""
        p1, p0, n, reps = 0.018, 0.015, 3000, 20_000
        k1 = RNG.binomial(n, p1, size=reps)
        k0 = RNG.binomial(n, p0, size=reps)
        truth = p1 - p0
        covered = 0
        for a, b in zip(k1, k0, strict=True):
            ci = freq.newcombe_ci(int(a), n, int(b), n)
            covered += ci.lo <= truth <= ci.hi
        assert covered / reps == pytest.approx(0.95, abs=0.01)

    def test_newcombe_never_undercovers_in_zero_click_regime(self) -> None:
        """With ~2-3 expected clicks per arm, score intervals go conservative
        (over-cover) due to discreteness — acceptable; under-coverage is not."""
        p1, p0, n, reps = 0.004, 0.003, 800, 20_000
        k1 = RNG.binomial(n, p1, size=reps)
        k0 = RNG.binomial(n, p0, size=reps)
        truth = p1 - p0
        covered = 0
        for a, b in zip(k1, k0, strict=True):
            ci = freq.newcombe_ci(int(a), n, int(b), n)
            covered += ci.lo <= truth <= ci.hi
        assert covered / reps >= 0.95

    def test_relative_lift_ci_coverage(self) -> None:
        p1, p0, n, reps = 0.018, 0.015, 3000, 10_000
        truth = p1 / p0 - 1
        k1 = RNG.binomial(n, p1, size=reps)
        k0 = RNG.binomial(n, p0, size=reps)
        covered = usable = 0
        for a, b in zip(k1, k0, strict=True):
            res = freq.relative_lift_ci(int(a), n, int(b), n)
            if res is None:
                continue
            usable += 1
            covered += res[1].lo <= truth <= res[1].hi
        assert usable > 0.99 * reps
        assert covered / usable == pytest.approx(0.95, abs=0.01)


class TestEdgeCases:
    def test_zero_clicks_everywhere(self) -> None:
        assert freq.two_prop_ztest(0, 100, 0, 100).p_value == 1.0
        assert freq.wilson_ci(0, 100).lo == 0.0
        assert freq.relative_lift_ci(0, 100, 5, 100) is None
        assert freq.lift_estimate(0, 100, 5, 100).rel_lift is None
        _, p = freq.chi_square_karm([0, 0], [100, 100])
        assert p == 1.0

    def test_input_validation(self) -> None:
        with pytest.raises(ValueError):
            freq.wilson_ci(5, 0)
        with pytest.raises(ValueError):
            freq.wilson_ci(11, 10)
        with pytest.raises(ValueError):
            freq.chi_square_karm([1], [10])
