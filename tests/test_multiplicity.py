"""Validate Holm and BH adjusted p-values against statsmodels."""

import numpy as np
import pytest
from statsmodels.stats.multitest import multipletests

from abkit import multiplicity

RNG = np.random.default_rng(11)


@pytest.mark.parametrize("size", [1, 2, 5, 40, 500])
def test_holm_matches_statsmodels(size: int) -> None:
    p = RNG.uniform(size=size)
    ours = multiplicity.holm(p)
    _, ref, _, _ = multipletests(p, method="holm")
    np.testing.assert_allclose(ours, ref, atol=1e-12)


@pytest.mark.parametrize("size", [1, 2, 5, 40, 500])
def test_bh_matches_statsmodels(size: int) -> None:
    p = RNG.uniform(size=size)
    ours = multiplicity.benjamini_hochberg(p)
    _, ref, _, _ = multipletests(p, method="fdr_bh")
    np.testing.assert_allclose(ours, ref, atol=1e-12)


def test_bh_controls_fdr_by_simulation() -> None:
    """Global null: BH at q=0.05 should make any discovery in <=5% of runs."""
    reps, m = 4000, 20
    false_discovery_runs = 0
    for _ in range(reps):
        p = RNG.uniform(size=m)
        false_discovery_runs += bool((multiplicity.benjamini_hochberg(p) < 0.05).any())
    assert false_discovery_runs / reps <= 0.05 + 0.01


def test_ties_and_bounds() -> None:
    p = np.array([0.01, 0.01, 0.9, 1.0])
    for adj in (multiplicity.holm(p), multiplicity.benjamini_hochberg(p)):
        assert (adj >= p - 1e-15).all()
        assert (adj <= 1.0).all()


def test_input_validation() -> None:
    with pytest.raises(ValueError):
        multiplicity.holm([])
    with pytest.raises(ValueError):
        multiplicity.benjamini_hochberg([0.5, 1.5])
