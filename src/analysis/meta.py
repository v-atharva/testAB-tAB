"""Corpus-level meta-analysis: the five questions, with figures.

1. Winner's curse — naive vs shrinkage-corrected winner lift.
2. Power — what fraction of tests could detect the lifts that actually occur?
3. False discovery accounting — how many "wins" evaporate under correction?
4. Peeking damage — simulated stopping rules on corpus-realistic streams,
   plus conditional-permutation replays of the real tests.
5. SRM audit — allocation anomalies across the whole archive.

Plus a small, clearly-labeled sidebar: headline features of corrected winners.
Every figure lands in outputs/figures/{set}/ and every headline number in
outputs/results/{set}_summary.{md,json}.
"""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
import pandas as pd

from abkit import multiplicity, sequential
from analysis import figstyle
from analysis.config import AppConfig
from analysis.paths import FIGURES_DIR, RESULTS_DIR

PEEK_LOOKS = 20


# ---------------------------------------------------------------- winner's curse


def winners_curse(tests: pd.DataFrame, set_name: str, summary: dict[str, Any]) -> None:
    win = tests[tests["sig_corrected"] & tests["winner_rel_lift_naive"].notna()].copy()
    if win.empty:
        summary["winners_curse"] = {"n_winners": 0}
        return
    naive = win["winner_rel_lift_naive"].to_numpy(dtype=float)
    shrunk = win["winner_rel_lift_shrunk"].to_numpy(dtype=float)
    ratio = naive / shrunk
    med_ratio = float(np.median(ratio))
    med_excess_pp = float(np.median(naive - shrunk)) * 100

    # exaggeration vs power (all tests with an observed non-baseline winner,
    # not only significant ones — selection operates everywhere)
    all_win = tests[tests["winner_rel_lift_naive"].notna()
                    & tests["winner_rel_lift_shrunk"].notna()].copy()
    all_win["exagg"] = all_win["winner_rel_lift_naive"] / all_win["winner_rel_lift_shrunk"]
    all_win = all_win[(all_win["winner_rel_lift_shrunk"] > 0)]
    bins = [float(b) for b in np.unique(np.quantile(all_win["achieved_power"],
                                                    np.linspace(0, 1, 9)))]
    grouped = all_win.groupby(pd.cut(all_win["achieved_power"], bins), observed=True)
    binned = grouped.agg(power=("achieved_power", "median"), exagg=("exagg", "median"))

    import matplotlib.pyplot as plt

    figstyle.apply_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.4))
    lim = float(np.percentile(naive, 98)) * 100
    ax1.scatter(naive * 100, shrunk * 100, s=14, alpha=0.45, color=figstyle.BLUE,
                edgecolors="none")
    ax1.plot([0, lim], [0, lim], ls="--", lw=1.2, color=figstyle.MUTED)
    ax1.annotate("y = x (no exaggeration)", xy=(lim * 0.72, lim * 0.75), fontsize=8.5,
                 color=figstyle.INK_SECONDARY, rotation=38)
    ax1.set_xlim(0, lim)
    ax1.set_ylim(0, lim)
    ax1.set_xlabel("naive winner lift (relative, %)")
    ax1.set_ylabel("shrinkage-corrected lift (%)")
    ax1.set_title(f"Corrected winners still overstate: median x{med_ratio:.2f}")

    ax2.plot(binned["power"], binned["exagg"], color=figstyle.BLUE, marker="o", ms=5)
    ax2.axhline(1.0, ls="--", lw=1.2, color=figstyle.MUTED)
    ax2.set_xlabel("achieved power vs corpus-typical lift")
    ax2.set_ylabel("median exaggeration ratio (naive / corrected)")
    ax2.set_title("Exaggeration is a low-power disease")
    fig.suptitle("")
    out = FIGURES_DIR / set_name
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "winners_curse.png")
    plt.close(fig)

    summary["winners_curse"] = {
        "n_corrected_winners": len(win),
        "median_exaggeration_ratio": round(med_ratio, 3),
        "median_naive_rel_lift": round(float(np.median(naive)), 4),
        "median_shrunk_rel_lift": round(float(np.median(shrunk)), 4),
        "median_excess_rel_lift_pp": round(med_excess_pp, 2),
    }


# ------------------------------------------------------------------------- power


def power_audit(tests: pd.DataFrame, set_name: str, summary: dict[str, Any]) -> None:
    import matplotlib.pyplot as plt

    ok = tests[~tests["srm_failed"]]
    frac_adequate = float((ok["achieved_power"] >= 0.8).mean())
    median_power = float(ok["achieved_power"].median())

    figstyle.apply_style()
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    ax.hist(ok["achieved_power"], bins=40, color=figstyle.BLUE, edgecolor=figstyle.SURFACE,
            linewidth=0.4)
    ax.axvline(0.8, ls="--", lw=1.4, color=figstyle.INK_SECONDARY)
    ax.annotate(f"80% planning bar\n{frac_adequate:.0%} of tests reach it",
                xy=(0.8, ax.get_ylim()[1] * 0.85), fontsize=9,
                color=figstyle.INK_SECONDARY, ha="left",
                xytext=(0.55, ax.get_ylim()[1] * 0.82))
    ax.set_xlabel("achieved power to detect a corpus-typical lift (one prior sd)")
    ax.set_ylabel("experiments")
    ax.set_title(f"Median experiment had {median_power:.0%} power for realistic effects")
    fig.savefig(FIGURES_DIR / set_name / "power_distribution.png")
    plt.close(fig)

    summary["power"] = {
        "median_achieved_power": round(median_power, 3),
        "frac_tests_power_ge_80": round(frac_adequate, 4),
    }


# --------------------------------------------------------------- FDR accounting


def fdr_accounting(tests: pd.DataFrame, set_name: str, summary: dict[str, Any]) -> None:
    import matplotlib.pyplot as plt

    ok = tests[~tests["srm_failed"]].copy()
    n_uncorrected = int(ok["sig_uncorrected"].sum())
    n_holm = int(ok["sig_corrected"].sum())
    # corpus-level: BH over each test's Holm-adjusted min p among POSITIVE-lift
    # comparisons (a valid per-test p for "this test has a winner"), q = 0.05.
    # Direction-consistent with the two counts above.
    valid = ok["min_holm_p_pos"].dropna()
    bh = multiplicity.benjamini_hochberg(valid.to_numpy())
    n_bh = int((bh < 0.05).sum())

    labels = [
        "uncorrected\n(any pairwise p < .05)",
        "within-test Holm",
        "+ BH across the corpus",
    ]
    counts = [n_uncorrected, n_holm, n_bh]
    # ordinal ramp (sequential blue steps 650/450/250): increasing strictness
    colors = ["#9ec5f4", "#5598e7", "#256abf"]

    figstyle.apply_style()
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    bars = ax.barh(labels[::-1], counts[::-1], color=colors[::-1], height=0.62)
    for b, c in zip(bars, counts[::-1], strict=True):
        ax.annotate(f"{c:,}", xy=(b.get_width(), b.get_y() + b.get_height() / 2),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=10,
                    color=figstyle.INK)
    evaporated = 1 - n_bh / n_uncorrected if n_uncorrected else 0.0
    ax.set_title(f'"Wins" under increasingly honest accounting — '
                 f"{evaporated:.0%} of naive wins evaporate")
    ax.set_xlabel("experiments with a declared winner")
    ax.grid(axis="y", visible=False)
    fig.savefig(FIGURES_DIR / set_name / "fdr_accounting.png")
    plt.close(fig)

    summary["fdr"] = {
        "wins_uncorrected": n_uncorrected,
        "wins_holm": n_holm,
        "wins_holm_plus_bh": n_bh,
        "frac_naive_wins_evaporating": round(evaporated, 4),
    }


# ---------------------------------------------------------------------- peeking


def peeking_damage(
    tests: pd.DataFrame,
    df_raw: pd.DataFrame,
    cfg: AppConfig,
    set_name: str,
    summary: dict[str, Any],
) -> None:
    import matplotlib.pyplot as plt

    rng = np.random.default_rng(cfg.replay_seed)

    # -- Panel A: pure simulation with KNOWN null, corpus-realistic sizes ------
    arm_sizes = df_raw.groupby("test_id")["impressions"].min().to_numpy()
    n_sims = 2000
    look_grid = [1, 2, 5, 10, 20, 50]
    max_looks = max(look_grid)
    naive_rate = dict.fromkeys(look_grid, 0)
    msprt_rate = 0
    for _ in range(n_sims):
        p0 = float(np.clip(rng.beta(cfg.readout.ctr_prior.a, cfg.readout.ctr_prior.b),
                           0.001, 0.2))
        n = int(rng.choice(arm_sizes))
        looks = sequential.replay_looks(n, max_looks)
        x1 = np.cumsum(rng.binomial(1, p0, size=n))[looks - 1]
        x0 = np.cumsum(rng.binomial(1, p0, size=n))[looks - 1]
        for lk in look_grid:
            # lk looks at fractions 1/lk, 2/lk, ..., 1 of the data — the LAST
            # look is always the full sample (lk=1 == the fixed-n test)
            idx = (np.arange(1, lk + 1) * max_looks // lk) - 1
            if sequential.naive_peeking_rejections(
                x1[idx], looks[idx], x0[idx], looks[idx], cfg.alpha
            ) is not None:
                naive_rate[lk] += 1
        trace = sequential.msprt_two_prop(x1, looks, x0, looks,
                                          phi=cfg.mixture_phi, alpha=cfg.alpha)
        msprt_rate += trace.first_rejection is not None
    naive_curve = {lk: v / n_sims for lk, v in naive_rate.items()}
    msprt_fp = msprt_rate / n_sims

    # -- Panel B: conditional-permutation replay of the REAL tests -------------
    # Benchmark: the full-sample corrected verdict. "Phantom win" = an interim
    # naive p<.05 in a test whose complete data shows no corrected winner.
    no_win = tests[~tests["sig_corrected"] & ~tests["srm_failed"]]["test_id"]
    sub = df_raw[df_raw["test_id"].isin(no_win) & (df_raw["arm_idx"] <= 1)]
    phantom_naive = phantom_msprt = n_replayed = 0
    for _, g in sub.groupby("test_id", sort=False):
        if len(g) != 2:
            continue
        g = g.sort_values("arm_idx")
        n_replayed += 1
        k1 = sequential.conditional_permutation_replay(
            int(g["clicks"].iloc[1]), int(g["impressions"].iloc[1]), PEEK_LOOKS, rng)
        k0 = sequential.conditional_permutation_replay(
            int(g["clicks"].iloc[0]), int(g["impressions"].iloc[0]), PEEK_LOOKS, rng)
        n1 = sequential.replay_looks(int(g["impressions"].iloc[1]), PEEK_LOOKS)
        n0 = sequential.replay_looks(int(g["impressions"].iloc[0]), PEEK_LOOKS)
        if sequential.naive_peeking_rejections(k1, n1, k0, n0, cfg.alpha) is not None:
            phantom_naive += 1
        if sequential.msprt_two_prop(k1, n1, k0, n0, phi=cfg.mixture_phi,
                                     alpha=cfg.alpha).first_rejection is not None:
            phantom_msprt += 1

    figstyle.apply_style()
    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    ax.plot(list(naive_curve), [v * 100 for v in naive_curve.values()],
            color=figstyle.ORANGE, marker="o", ms=5, label="naive: stop at first p < 0.05")
    ax.axhline(msprt_fp * 100, color=figstyle.BLUE, lw=2,
               label="mSPRT (always-valid), monitored at every look")
    ax.axhline(cfg.alpha * 100, ls="--", lw=1.2, color=figstyle.MUTED)
    ax.annotate("nominal 5%", xy=(1.1, cfg.alpha * 100 + 0.6), fontsize=8.5,
                color=figstyle.INK_SECONDARY)
    ax.set_xscale("log")
    ax.set_xticks(look_grid)
    ax.set_xticklabels([str(x) for x in look_grid])
    ax.set_xlabel("number of interim looks")
    ax.set_ylabel("false-positive rate under a true null (%)")
    ax.set_title("Peeking inflates naive false positives; mSPRT does not")
    ax.legend()
    fig.savefig(FIGURES_DIR / set_name / "peeking_damage.png")
    plt.close(fig)

    summary["peeking"] = {
        "sim_naive_fp_by_looks": {str(k): round(v, 4) for k, v in naive_curve.items()},
        "sim_msprt_fp_continuous": round(msprt_fp, 4),
        "replay_tests_without_corrected_winner": n_replayed,
        "replay_phantom_win_rate_naive": round(phantom_naive / n_replayed, 4)
        if n_replayed else None,
        "replay_phantom_win_rate_msprt": round(phantom_msprt / n_replayed, 4)
        if n_replayed else None,
    }


# -------------------------------------------------------------------- SRM audit


def srm_audit(tests: pd.DataFrame, set_name: str, summary: dict[str, Any]) -> None:
    import matplotlib.pyplot as plt

    rate = float(tests["srm_failed"].mean())
    n_failed = int(tests["srm_failed"].sum())

    figstyle.apply_style()
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.hist(tests["srm_p"], bins=50, color=figstyle.BLUE, edgecolor=figstyle.SURFACE,
            linewidth=0.4)
    ax.axhline(len(tests) / 50, ls="--", lw=1.4, color=figstyle.MUTED)
    ax.annotate("expected if allocation were exactly uniform", fontsize=8.5,
                xy=(0.35, len(tests) / 50), xytext=(0.35, len(tests) / 50 * 1.35),
                color=figstyle.INK_SECONDARY)
    ax.set_xlabel("SRM p-value (chi-square vs even split)")
    ax.set_ylabel("experiments")
    ax.set_title(
        f"SRM audit: {n_failed:,} of {len(tests):,} tests ({rate:.1%}) fail at p < 0.001"
    )
    fig.savefig(FIGURES_DIR / set_name / "srm_audit.png")
    plt.close(fig)

    summary["srm"] = {"n_failed": n_failed, "rate": round(rate, 4)}


# ---------------------------------------------------- headline features (sidebar)


FEATURES: dict[str, Any] = {
    "question": lambda h: "?" in h,
    "exclamation": lambda h: "!" in h,
    "number": lambda h: bool(re.search(r"\d", h)),
    # curly quotes appear verbatim in Upworthy headlines
    "quotation": lambda h: any(q in h for q in ('"', "'", "‘", "“")),  # noqa: RUF001
    "all_caps_word": lambda h: bool(re.search(r"\b[A-Z]{3,}\b", h)),
    "demonstrative": lambda h: bool(
        re.search(r"\b(this|these|here's|heres)\b", h, re.IGNORECASE)
    ),
    "second_person": lambda h: bool(re.search(r"\byou(r|'ll|'re)?\b", h, re.IGNORECASE)),
}


def headline_features(
    tests: pd.DataFrame, arms: pd.DataFrame, df_raw: pd.DataFrame,
    set_name: str, summary: dict[str, Any],
) -> None:
    """Winner-vs-baseline headline features among corrected winners.

    Restricted to tests where the headline varied and the image did not, so
    the headline is the treatment. Paired sign test per feature, BH-corrected.
    Sidebar analysis: descriptive, not causal — features are correlated.
    """
    import matplotlib.pyplot as plt
    from scipy import stats

    per_test = df_raw.groupby("test_id").agg(
        headline_varies=("headline", lambda s: s.nunique() > 1),
        image_varies=("eyecatcher_id", lambda s: s.nunique() > 1),
    )
    eligible = per_test[per_test["headline_varies"] & ~per_test["image_varies"]].index
    win_tests = tests[tests["sig_corrected"] & tests["test_id"].isin(eligible)]

    merged = arms.merge(
        win_tests[["test_id", "best_arm_idx"]], on="test_id", how="inner"
    )
    rows = []
    for _, g in merged.groupby("test_id"):
        base = g[g["arm_idx"] == 0]
        best = g[g["arm_idx"] == g["best_arm_idx"]]
        if base.empty or best.empty or base.index.equals(best.index):
            continue
        rows.append((str(base["headline"].iloc[0]), str(best["headline"].iloc[0])))

    results = []
    for name, fn in FEATURES.items():
        gains = sum(fn(w) and not fn(b) for b, w in rows)
        losses = sum(fn(b) and not fn(w) for b, w in rows)
        n_disc = gains + losses
        p = float(stats.binomtest(gains, n_disc, 0.5).pvalue) if n_disc else 1.0
        results.append({"feature": name, "winner_gains": gains, "winner_drops": losses,
                        "discordant_pairs": n_disc, "p_sign_test": p})
    res = pd.DataFrame(results)
    res["q_bh"] = multiplicity.benjamini_hochberg(res["p_sign_test"].to_numpy())
    res["net_pp"] = (res["winner_gains"] - res["winner_drops"]) / max(len(rows), 1) * 100
    res = res.sort_values("net_pp")
    res.to_csv(RESULTS_DIR / f"{set_name}_headline_features.csv", index=False)

    figstyle.apply_style()
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.barh(res["feature"], res["net_pp"], color=figstyle.BLUE, height=0.6)
    ax.axvline(0, color=figstyle.AXIS, lw=1)
    for _, r in res.iterrows():
        if r["q_bh"] < 0.05:
            ax.annotate("q < .05", xy=(r["net_pp"], r["feature"]),
                        xytext=(4 if r["net_pp"] >= 0 else -30, -3),
                        textcoords="offset points", fontsize=8, color=figstyle.INK_SECONDARY)
    ax.set_xlabel("net % of winning headlines that added the feature (vs baseline)")
    ax.set_title(f"What corrected winners changed (n={len(rows)} headline-only tests)")
    ax.grid(axis="y", visible=False)
    fig.savefig(FIGURES_DIR / set_name / "headline_features.png")
    plt.close(fig)

    summary["headline_features"] = {
        "n_paired_tests": len(rows),
        "significant_features_bh": res.loc[res["q_bh"] < 0.05, "feature"].tolist(),
    }


# ----------------------------------------------------------- upworthy comparison


def upworthy_audit(tests: pd.DataFrame, summary: dict[str, Any]) -> None:
    declared = tests[tests["upworthy_declared_winner"]]
    if declared.empty:
        summary["upworthy_audit"] = {"n_declared": 0}
        return
    # "confirmed" covers both directions of agreement: their winner is a
    # variant our corrected analysis also crowns, OR their winner is the
    # baseline arm and our verdict is keep-baseline.
    variant_confirmed = (
        (declared["upworthy_winner_arm_idx"] == declared["best_arm_idx"])
        & declared["sig_corrected"]
    )
    baseline_confirmed = (declared["upworthy_winner_arm_idx"] == 0) & (
        declared["verdict"] == "keep_baseline"
    )
    summary["upworthy_audit"] = {
        "n_declared": len(declared),
        "frac_of_tests": round(float(len(declared) / len(tests)), 4),
        "frac_winner_is_baseline_arm": round(
            float((declared["upworthy_winner_arm_idx"] == 0).mean()), 4
        ),
        "frac_confirmed_by_corrected_analysis": round(
            float((variant_confirmed | baseline_confirmed).mean()), 4
        ),
        "frac_underpowered_verdict": round(
            float((declared["verdict"] == "underpowered").mean()), 4
        ),
        "frac_srm_failed": round(float(declared["srm_failed"].mean()), 4),
    }


# ----------------------------------------------------------------------- driver


def run_meta(
    tests: pd.DataFrame, arms: pd.DataFrame, df_raw: pd.DataFrame,
    cfg: AppConfig, set_name: str,
) -> dict[str, Any]:
    (FIGURES_DIR / set_name).mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "dataset": set_name,
        "n_tests": len(tests),
        "n_arms": len(arms),
        "verdict_counts": tests["verdict"].value_counts().to_dict(),
    }
    winners_curse(tests, set_name, summary)
    power_audit(tests, set_name, summary)
    fdr_accounting(tests, set_name, summary)
    peeking_damage(tests, df_raw, cfg, set_name, summary)
    srm_audit(tests, set_name, summary)
    headline_features(tests, arms, df_raw, set_name, summary)
    upworthy_audit(tests, summary)

    with (RESULTS_DIR / f"{set_name}_summary.json").open("w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"[meta:{set_name}] summary -> {RESULTS_DIR / f'{set_name}_summary.json'}")
    return summary
