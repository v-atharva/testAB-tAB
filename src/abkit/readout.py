"""Compose abkit's pieces into one decision-grade experiment readout.

The verdict logic, in priority order (health before inference, always):

1. SRM failed                    -> INVALID_SRM       (do not read any lift)
2. Below minimum-sample gates    -> INSUFFICIENT_DATA
3. Best arm beats baseline after Holm correction -> SHIP_VARIANT
4. No variant beats baseline; adequately powered -> KEEP_BASELINE
5. No significant difference and underpowered    -> UNDERPOWERED (don't conclude)

"Adequately powered" is judged against the corpus benchmark lift: a
one-prior-sd true lift (exp(tau) - 1 relative), i.e. the size of effect that
actually occurs in this corpus — not an arbitrary MDE.

Baseline convention: arm 0 is the baseline (the analysis layer orders arms by
created_at, earliest first — the "incumbent"). The Upworthy archive does not
designate a control; this convention is documented in the UI and the user can
re-pick the baseline in the dashboard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from abkit import bayes, design, freq, health, multiplicity, shrinkage


class Verdict(Enum):
    SHIP_VARIANT = "ship_variant"
    KEEP_BASELINE = "keep_baseline"
    UNDERPOWERED = "underpowered"
    INVALID_SRM = "invalid_srm"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class ArmCounts:
    name: str
    impressions: int
    clicks: int


@dataclass(frozen=True)
class ReadoutConfig:
    alpha: float
    srm_alpha: float
    min_impressions_per_arm: int
    min_total_impressions: int
    underpowered_below: float
    mc_draws: int
    seed: int
    lift_prior: shrinkage.NormalPrior  # corpus prior on true log-odds lifts
    ctr_prior: bayes.BetaPrior  # corpus prior on CTRs


@dataclass(frozen=True)
class ArmReadout:
    name: str
    impressions: int
    clicks: int
    ctr: float
    ctr_ci: freq.ConfInt
    post_mean_ctr: float
    p_best: float
    expected_loss: float


@dataclass(frozen=True)
class Comparison:
    """One variant vs the baseline arm."""

    arm_index: int
    z_p_value: float
    holm_p_value: float
    abs_lift: float
    abs_lift_ci: freq.ConfInt
    rel_lift: float | None
    rel_lift_ci: freq.ConfInt | None
    shrunk_rel_lift: float | None  # empirical-Bayes posterior mean, relative scale
    shrunk_rel_ci: tuple[float, float] | None
    significant: bool  # after Holm correction, at cfg.alpha


@dataclass(frozen=True)
class Readout:
    arms: list[ArmReadout]
    baseline_index: int
    comparisons: list[Comparison]
    omnibus_chi2_p: float
    srm: health.SrmResult
    quality: health.QualityReport
    achieved_power: float
    benchmark_rel_lift: float  # the corpus-typical lift the power refers to
    verdict: Verdict
    best_arm_index: int
    headline: str
    notes: list[str]


def _fmt_pct(x: float) -> str:
    return f"{100 * x:+.1f}%"


def _theta_to_rel(theta: float) -> float:
    """Log-odds lift -> relative CTR lift (odds-ratio ~= risk-ratio at ~1.5% CTR)."""
    return math.exp(theta) - 1.0


def analyze_experiment(arms: list[ArmCounts], cfg: ReadoutConfig) -> Readout:
    """Full decision-grade readout for one k-arm experiment (arm 0 = baseline)."""
    if len(arms) < 2:
        raise ValueError("an experiment needs at least 2 arms")
    ks = [a.clicks for a in arms]
    ns = [a.impressions for a in arms]

    srm = health.srm_test(ns, alpha=cfg.srm_alpha)
    quality = health.quality_report(
        ks,
        ns,
        min_impressions_per_arm=cfg.min_impressions_per_arm,
        min_total_impressions=cfg.min_total_impressions,
    )
    _, omnibus_p = freq.chi_square_karm(ks, ns)
    bay = bayes.bayes_readout(ks, ns, cfg.ctr_prior, mc_draws=cfg.mc_draws, seed=cfg.seed)

    arm_readouts = [
        ArmReadout(
            name=a.name,
            impressions=a.impressions,
            clicks=a.clicks,
            ctr=a.clicks / a.impressions,
            ctr_ci=freq.wilson_ci(a.clicks, a.impressions, cfg.alpha),
            post_mean_ctr=bay.post_mean[i],
            p_best=bay.p_best[i],
            expected_loss=bay.expected_loss[i],
        )
        for i, a in enumerate(arms)
    ]

    k0, n0 = ks[0], ns[0]
    raw_ps: list[float] = []
    for i in range(1, len(arms)):
        raw_ps.append(freq.two_prop_ztest(ks[i], ns[i], k0, n0).p_value)
    holm_ps = multiplicity.holm(raw_ps)

    comparisons: list[Comparison] = []
    for j, i in enumerate(range(1, len(arms))):
        est = freq.lift_estimate(ks[i], ns[i], k0, n0, cfg.alpha)
        lo = shrinkage.log_odds_lift(ks[i], ns[i], k0, n0)
        if lo is None:
            shrunk_rel, shrunk_ci = None, None
        else:
            post = shrinkage.shrink(lo[0], lo[1], cfg.lift_prior)
            s_lo, s_hi = post.interval(cfg.alpha)
            shrunk_rel = _theta_to_rel(post.post_mean)
            shrunk_ci = (_theta_to_rel(s_lo), _theta_to_rel(s_hi))
        comparisons.append(
            Comparison(
                arm_index=i,
                z_p_value=raw_ps[j],
                holm_p_value=float(holm_ps[j]),
                abs_lift=est.abs_lift,
                abs_lift_ci=est.abs_ci,
                rel_lift=est.rel_lift,
                rel_lift_ci=est.rel_ci,
                shrunk_rel_lift=shrunk_rel,
                shrunk_rel_ci=shrunk_ci,
                significant=float(holm_ps[j]) < cfg.alpha,
            )
        )

    # Achieved power vs the corpus-benchmark lift (one prior sd on log-odds),
    # at the smallest variant/baseline pairing actually run.
    benchmark_rel = _theta_to_rel(cfg.lift_prior.tau)
    p_base = max(1e-6, min(1 - 1e-6, k0 / n0))
    n_pair = min(min(ns[1:]), n0)
    p_alt = min(1 - 1e-6, p_base * (1 + benchmark_rel))
    achieved_power = (
        design.power_two_prop(p_base, p_alt, n_pair, cfg.alpha) if p_alt > p_base else cfg.alpha
    )

    best_idx = max(range(len(arms)), key=lambda i: arm_readouts[i].ctr)
    verdict, headline, notes = _decide(
        arms, arm_readouts, comparisons, srm, quality, achieved_power, benchmark_rel, best_idx, cfg
    )
    return Readout(
        arms=arm_readouts,
        baseline_index=0,
        comparisons=comparisons,
        omnibus_chi2_p=omnibus_p,
        srm=srm,
        quality=quality,
        achieved_power=achieved_power,
        benchmark_rel_lift=benchmark_rel,
        verdict=verdict,
        best_arm_index=best_idx,
        headline=headline,
        notes=notes,
    )


def _decide(
    arms: list[ArmCounts],
    arm_readouts: list[ArmReadout],
    comparisons: list[Comparison],
    srm: health.SrmResult,
    quality: health.QualityReport,
    achieved_power: float,
    benchmark_rel: float,
    best_idx: int,
    cfg: ReadoutConfig,
) -> tuple[Verdict, str, list[str]]:
    notes: list[str] = []

    if srm.failed:
        return (
            Verdict.INVALID_SRM,
            "Invalid experiment — traffic split does not match the plan (SRM). "
            "Do not read any result from this test.",
            [
                f"Chi-square p = {srm.p_value:.2e} against an even split "
                f"(threshold {cfg.srm_alpha}). Something broke in assignment or "
                "logging; lifts from this test are not trustworthy."
            ],
        )
    if quality.gated:
        return (
            Verdict.INSUFFICIENT_DATA,
            "Not enough data to conclude anything — this test never reached the minimum sample.",
            list(quality.reasons),
        )

    baseline = arms[0].name
    sig_winners = [c for c in comparisons if c.significant and c.abs_lift > 0]
    if sig_winners:
        top = max(sig_winners, key=lambda c: c.abs_lift)
        arm = arms[top.arm_index].name
        naive = _fmt_pct(top.rel_lift) if top.rel_lift is not None else "n/a"
        shrunk = _fmt_pct(top.shrunk_rel_lift) if top.shrunk_rel_lift is not None else "n/a"
        notes.append(
            f"'{arm}' beats '{baseline}' after Holm correction across "
            f"{len(comparisons)} comparisons (adjusted p = {top.holm_p_value:.3g})."
        )
        notes.append(
            f"Naive relative lift {naive}; shrinkage-corrected estimate {shrunk}. "
            "Plan around the corrected number — the naive one is selected for being big."
        )
        return Verdict.SHIP_VARIANT, f"Ship '{arm}' — corrected lift {shrunk} vs baseline.", notes

    adequately_powered = achieved_power >= cfg.underpowered_below
    if adequately_powered:
        notes.append(
            f"No variant beats the baseline after correction, and the test had "
            f"{achieved_power:.0%} power to detect a corpus-typical lift "
            f"({_fmt_pct(benchmark_rel)} relative)."
        )
        return (
            Verdict.KEEP_BASELINE,
            f"Keep '{baseline}' — no variant shows a corrected, significant improvement.",
            notes,
        )

    notes.append(
        f"Power to detect a corpus-typical lift ({_fmt_pct(benchmark_rel)} relative) was only "
        f"{achieved_power:.0%} — well under the {cfg.underpowered_below:.0%} bar. "
        "Absence of significance here is NOT evidence of no effect."
    )
    if best_idx != 0:
        notes.append(
            f"'{arms[best_idx].name}' looks best (P(best) = {arm_readouts[best_idx].p_best:.0%}, "
            f"expected CTR loss if shipped anyway: "
            f"{arm_readouts[best_idx].expected_loss * 100:.3f} pp) — a defensible forced pick, "
            "not a significant winner."
        )
    return (
        Verdict.UNDERPOWERED,
        "Underpowered — don't conclude. The test ended before it could detect realistic lifts.",
        notes,
    )
