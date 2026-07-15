"""Run the abkit readout over every experiment in a dataset.

Produces two parquet files under outputs/results/:

* {set}_tests.parquet — one row per experiment: verdict, health, power,
  naive vs shrunk winner lift, correction outcomes, Upworthy's own call.
* {set}_arms.parquet  — one row per arm: CTRs, CIs, Bayesian quantities,
  and per-comparison stats vs the baseline arm.

The dashboard and the meta-analysis read ONLY these files (plus the raw
counts for the sequential replay) — they never re-derive statistics.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from abkit.readout import ArmCounts, Readout, analyze_experiment
from analysis.config import AppConfig
from analysis.ingest import load_processed
from analysis.paths import RESULTS_DIR


def _test_row(test_id: str, g: pd.DataFrame, r: Readout) -> dict[str, Any]:
    comps = r.comparisons
    best_comp = next((c for c in comps if c.arm_index == r.best_arm_index), None)
    min_raw_p = min((c.z_p_value for c in comps), default=math.nan)
    min_holm_p = min((c.holm_p_value for c in comps), default=math.nan)
    # direction-consistent versions: evidence FOR a positive winner only
    pos = [c for c in comps if c.abs_lift > 0]
    min_raw_p_pos = min((c.z_p_value for c in pos), default=math.nan)
    min_holm_p_pos = min((c.holm_p_value for c in pos), default=math.nan)
    return {
        "test_id": test_id,
        "n_arms": len(r.arms),
        "total_impressions": int(g["impressions"].sum()),
        "total_clicks": int(g["clicks"].sum()),
        "baseline_ctr": r.arms[0].ctr,
        "test_week": int(g["test_week"].min()),
        "first_created_at": g["created_at"].min(),
        "verdict": r.verdict.value,
        "verdict_headline": r.headline,
        "srm_p": r.srm.p_value,
        "srm_failed": r.srm.failed,
        "omnibus_p": r.omnibus_chi2_p,
        "achieved_power": r.achieved_power,
        "best_arm_idx": r.best_arm_index,
        "best_arm_p_best": r.arms[r.best_arm_index].p_best,
        "min_raw_p": min_raw_p,
        "min_holm_p": min_holm_p,
        "min_raw_p_pos": min_raw_p_pos,
        "min_holm_p_pos": min_holm_p_pos,
        # naive vs shrunk lift of the OBSERVED BEST arm vs baseline (None when
        # the best arm IS the baseline, or when a zero-click cell blocks it)
        "winner_rel_lift_naive": best_comp.rel_lift if best_comp else None,
        "winner_rel_lift_shrunk": best_comp.shrunk_rel_lift if best_comp else None,
        "winner_raw_p": best_comp.z_p_value if best_comp else None,
        "winner_holm_p": best_comp.holm_p_value if best_comp else None,
        "sig_uncorrected": bool(
            any(c.z_p_value < 0.05 and c.abs_lift > 0 for c in comps)
        ),
        "sig_corrected": bool(any(c.significant and c.abs_lift > 0 for c in comps)),
        "upworthy_declared_winner": bool(g["upworthy_winner"].any()),
        "upworthy_winner_arm_idx": (
            int(g.loc[g["upworthy_winner"], "arm_idx"].iloc[0])
            if g["upworthy_winner"].any()
            else None
        ),
    }


def _arm_rows(test_id: str, g: pd.DataFrame, r: Readout) -> list[dict[str, Any]]:
    comp_by_idx = {c.arm_index: c for c in r.comparisons}
    rows = []
    headlines = g.sort_values("arm_idx")["headline"].tolist()
    for i, arm in enumerate(r.arms):
        c = comp_by_idx.get(i)
        rows.append(
            {
                "test_id": test_id,
                "arm_idx": i,
                "headline": headlines[i],
                "impressions": arm.impressions,
                "clicks": arm.clicks,
                "ctr": arm.ctr,
                "ctr_lo": arm.ctr_ci.lo,
                "ctr_hi": arm.ctr_ci.hi,
                "post_mean_ctr": arm.post_mean_ctr,
                "p_best": arm.p_best,
                "expected_loss": arm.expected_loss,
                "raw_p": c.z_p_value if c else None,
                "holm_p": c.holm_p_value if c else None,
                "abs_lift": c.abs_lift if c else None,
                "abs_lift_lo": c.abs_lift_ci.lo if c else None,
                "abs_lift_hi": c.abs_lift_ci.hi if c else None,
                "rel_lift": c.rel_lift if c else None,
                "rel_lift_lo": c.rel_lift_ci.lo if c and c.rel_lift_ci else None,
                "rel_lift_hi": c.rel_lift_ci.hi if c and c.rel_lift_ci else None,
                "shrunk_rel_lift": c.shrunk_rel_lift if c else None,
                "shrunk_rel_lo": c.shrunk_rel_ci[0] if c and c.shrunk_rel_ci else None,
                "shrunk_rel_hi": c.shrunk_rel_ci[1] if c and c.shrunk_rel_ci else None,
                "significant_corrected": c.significant if c else None,
            }
        )
    return rows


def run_batch(dataset: str, cfg: AppConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = load_processed(dataset)
    test_rows: list[dict[str, Any]] = []
    arm_rows: list[dict[str, Any]] = []
    n_tests = df["test_id"].nunique()
    for i, (test_id, g) in enumerate(df.groupby("test_id", sort=False)):
        g = g.sort_values("arm_idx")
        arms = [
            ArmCounts(name=f"arm {idx}", impressions=int(imp), clicks=int(clk))
            for idx, imp, clk in zip(
                g["arm_idx"].tolist(), g["impressions"].tolist(), g["clicks"].tolist(),
                strict=True,
            )
        ]
        r = analyze_experiment(arms, cfg.readout)
        tid = str(test_id)
        test_rows.append(_test_row(tid, g, r))
        arm_rows.extend(_arm_rows(tid, g, r))
        if (i + 1) % 2000 == 0:
            print(f"[batch:{dataset}] {i + 1}/{n_tests} tests")

    tests = pd.DataFrame(test_rows)
    arms_df = pd.DataFrame(arm_rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tests.to_parquet(RESULTS_DIR / f"{dataset}_tests.parquet", index=False)
    arms_df.to_parquet(RESULTS_DIR / f"{dataset}_arms.parquet", index=False)
    print(f"[batch:{dataset}] wrote {len(tests)} test readouts, {len(arms_df)} arm rows")
    return tests, arms_df
