"""End-to-end verdict tests for the composed readout."""

import pytest

from abkit import bayes, readout, shrinkage
from abkit.readout import ArmCounts, ReadoutConfig, Verdict

CFG = ReadoutConfig(
    alpha=0.05,
    srm_alpha=0.001,
    min_impressions_per_arm=100,
    min_total_impressions=1000,
    underpowered_below=0.50,
    mc_draws=50_000,
    seed=1,
    lift_prior=shrinkage.NormalPrior(mu=0.0, tau2=0.04),  # tau=0.2 -> ~22% typical rel lift
    ctr_prior=bayes.BetaPrior(a=30.0, b=2000.0),
)


def test_clear_winner_ships() -> None:
    arms = [ArmCounts("A", 20_000, 300), ArmCounts("B", 20_000, 420)]
    r = readout.analyze_experiment(arms, CFG)
    assert r.verdict == Verdict.SHIP_VARIANT
    assert "B" in r.headline
    assert r.comparisons[0].significant
    # shrinkage pulls the naive estimate toward the prior mean
    assert r.comparisons[0].shrunk_rel_lift is not None
    assert r.comparisons[0].rel_lift is not None
    assert 0 < r.comparisons[0].shrunk_rel_lift < r.comparisons[0].rel_lift


def test_no_difference_with_big_sample_keeps_baseline() -> None:
    arms = [ArmCounts("A", 200_000, 3000), ArmCounts("B", 200_000, 3010)]
    r = readout.analyze_experiment(arms, CFG)
    assert r.verdict == Verdict.KEEP_BASELINE
    assert r.achieved_power > 0.9


def test_small_null_test_is_underpowered_not_negative() -> None:
    """The modal Upworthy case: ~3k impressions/arm, no real difference.
    The honest verdict is 'underpowered', NOT 'keep baseline'."""
    arms = [ArmCounts("A", 3000, 46), ArmCounts("B", 3000, 52)]
    r = readout.analyze_experiment(arms, CFG)
    assert r.verdict == Verdict.UNDERPOWERED
    assert any("NOT evidence of no effect" in n for n in r.notes)


def test_srm_invalidates_before_anything_else() -> None:
    # wildly skewed allocation with an otherwise "significant" lift
    arms = [ArmCounts("A", 10_000, 150), ArmCounts("B", 5_000, 200)]
    r = readout.analyze_experiment(arms, CFG)
    assert r.verdict == Verdict.INVALID_SRM


def test_minimum_sample_gate() -> None:
    arms = [ArmCounts("A", 60, 1), ArmCounts("B", 55, 3)]
    r = readout.analyze_experiment(arms, CFG)
    assert r.verdict == Verdict.INSUFFICIENT_DATA


def test_zero_click_arm_yields_readout_without_relative_lift() -> None:
    arms = [ArmCounts("A", 3000, 0), ArmCounts("B", 3000, 50)]
    r = readout.analyze_experiment(arms, CFG)
    assert r.comparisons[0].rel_lift is None
    assert r.comparisons[0].shrunk_rel_lift is None
    assert r.comparisons[0].abs_lift > 0  # absolute lift still defined


def test_k_arm_correction_is_applied() -> None:
    """A p~0.03 comparison that is significant alone must not survive Holm
    across 5 comparisons."""
    base = ArmCounts("A", 3000, 45)
    mild = ArmCounts("B", 3000, 68)  # ~ p 0.02-0.04 uncorrected
    fillers = [ArmCounts(c, 3000, 45) for c in "CDEF"]
    r = readout.analyze_experiment([base, mild, *fillers], CFG)
    c = r.comparisons[0]
    assert c.holm_p_value >= c.z_p_value
    if c.z_p_value < 0.05 < c.holm_p_value:
        assert r.verdict != Verdict.SHIP_VARIANT


def test_baseline_convention_is_arm_zero() -> None:
    arms = [ArmCounts("first-created", 20_000, 420), ArmCounts("later", 20_000, 300)]
    r = readout.analyze_experiment(arms, CFG)
    # baseline itself is best: no variant beats it
    assert r.verdict in (Verdict.KEEP_BASELINE, Verdict.UNDERPOWERED)
    assert r.best_arm_index == 0


def test_two_arm_minimum() -> None:
    with pytest.raises(ValueError):
        readout.analyze_experiment([ArmCounts("A", 100, 5)], CFG)
