"""Experiment health checks: SRM, minimum-sample gates, quality flags.

A failed health check invalidates a readout — it is reported before, and
instead of, any lift estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scipy import stats


@dataclass(frozen=True)
class SrmResult:
    """Sample-ratio-mismatch test: chi-square of impressions vs planned split.

    Upworthy assigned viewers to packages uniformly, so the expected split is
    equal across arms. SRM uses a strict alpha (default 1e-3, set in config):
    a positive is evidence the randomization or logging broke, which
    invalidates the experiment rather than deciding it.
    """

    statistic: float
    p_value: float
    failed: bool


@dataclass(frozen=True)
class QualityReport:
    """Per-test data-quality flags. `gated` means: refuse to conclude."""

    zero_click_arms: list[int]
    below_min_impressions: list[int]
    duplicate_stimuli_groups: list[list[int]]
    gated: bool
    reasons: list[str] = field(default_factory=list)


def srm_test(
    impressions: list[int],
    alpha: float = 0.001,
    expected_shares: list[float] | None = None,
) -> SrmResult:
    """Chi-square goodness-of-fit of observed impressions vs the planned split."""
    if len(impressions) < 2:
        raise ValueError("need at least 2 arms")
    if any(n < 0 for n in impressions):
        raise ValueError("impressions must be non-negative")
    total = sum(impressions)
    if total == 0:
        raise ValueError("no impressions")
    if expected_shares is None:
        expected = [total / len(impressions)] * len(impressions)
    else:
        if len(expected_shares) != len(impressions) or abs(sum(expected_shares) - 1.0) > 1e-9:
            raise ValueError("expected_shares must match arm count and sum to 1")
        expected = [total * s for s in expected_shares]
    res = stats.chisquare(impressions, f_exp=expected)
    p = float(res.pvalue)
    return SrmResult(statistic=float(res.statistic), p_value=p, failed=p < alpha)


def quality_report(
    clicks: list[int],
    impressions: list[int],
    stimuli: list[str] | None = None,
    min_impressions_per_arm: int = 100,
    min_total_impressions: int = 1000,
) -> QualityReport:
    """Data-quality flags for one experiment.

    Zero-click arms and duplicate stimuli are surfaced but do not gate the
    readout; insufficient sample does.
    """
    if len(clicks) != len(impressions):
        raise ValueError("clicks and impressions must have equal length")
    zero_click = [i for i, k in enumerate(clicks) if k == 0]
    small = [i for i, n in enumerate(impressions) if n < min_impressions_per_arm]

    dup_groups: list[list[int]] = []
    if stimuli is not None:
        seen: dict[str, list[int]] = {}
        for i, s in enumerate(stimuli):
            seen.setdefault(s, []).append(i)
        dup_groups = [idxs for idxs in seen.values() if len(idxs) > 1]

    reasons: list[str] = []
    if small:
        reasons.append(
            f"{len(small)} arm(s) below the {min_impressions_per_arm}-impression minimum"
        )
    if sum(impressions) < min_total_impressions:
        reasons.append(f"total impressions below the {min_total_impressions} minimum")
    return QualityReport(
        zero_click_arms=zero_click,
        below_min_impressions=small,
        duplicate_stimuli_groups=dup_groups,
        gated=bool(reasons),
        reasons=reasons,
    )
