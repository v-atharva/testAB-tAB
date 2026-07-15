"""Fit the corpus priors — on the EXPLORATORY set only — and freeze them.

Two priors, written to config/fitted_priors.yaml (committed):

* ctr_prior:  Beta(a, b) on per-arm CTR, by Beta-Binomial marginal MLE.
* lift_prior: Normal(mu, tau^2) on TRUE log-odds lifts of variants vs their
  within-test baseline, by marginal MLE with known per-lift sampling variance.

After this file is generated once, every downstream stage (readouts, dashboard,
the one-shot confirmatory run) treats the values as frozen method parameters.

Also runs a time-split calibration check (fit on the first half of test weeks,
evaluate z-scores of the second half): a misfit prior would show dispersion
far from 1. The result is printed and stored alongside the priors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from abkit import bayes, shrinkage
from analysis.config import FITTED_PRIORS_PATH
from analysis.ingest import load_processed


def collect_lifts(df: pd.DataFrame) -> pd.DataFrame:
    """theta_hat/se2 for every variant-vs-baseline pair with no empty cells."""
    rows: list[dict[str, float | str]] = []
    for test_id, g in df.groupby("test_id", sort=False):
        g = g.sort_values("arm_idx")
        base = g.iloc[0]
        for _, arm in g.iloc[1:].iterrows():
            res = shrinkage.log_odds_lift(
                int(arm["clicks"]), int(arm["impressions"]),
                int(base["clicks"]), int(base["impressions"]),
            )
            if res is not None:
                rows.append(
                    {"test_id": str(test_id), "theta_hat": res[0], "se2": res[1],
                     "test_week": int(arm["test_week"])}
                )
    return pd.DataFrame(rows)


def time_split_calibration(lifts: pd.DataFrame) -> float:
    """Fit on early weeks, score late weeks: sd of z = (theta_hat - mu) / sqrt(tau2 + se2).

    ~1.0 means the prior fitted on one era describes the next era's dispersion;
    >>1 would mean the prior is too tight to be trusted.
    """
    cut = lifts["test_week"].median()
    early, late = lifts[lifts["test_week"] <= cut], lifts[lifts["test_week"] > cut]
    prior = shrinkage.fit_normal_prior(
        early["theta_hat"].to_numpy(), early["se2"].to_numpy()
    )
    z = (late["theta_hat"] - prior.mu) / np.sqrt(prior.tau2 + late["se2"])
    return float(z.std())


def main() -> None:
    df = load_processed("exploratory")

    ctr_prior = bayes.fit_beta_prior(df["clicks"].tolist(), df["impressions"].tolist())
    print(f"[priors] CTR prior: Beta(a={ctr_prior.a:.2f}, b={ctr_prior.b:.2f}) "
          f"(mean {ctr_prior.mean:.4f})")

    lifts = collect_lifts(df)
    excluded = (df.groupby('test_id').size() - 1).sum() - len(lifts)
    print(f"[priors] {len(lifts)} usable lifts ({excluded} pairs excluded for empty cells)")
    lift_prior = shrinkage.fit_normal_prior(lifts["theta_hat"].to_numpy(), lifts["se2"].to_numpy())
    print(f"[priors] lift prior: Normal(mu={lift_prior.mu:.5f}, tau={lift_prior.tau:.5f}) — "
          f"a one-sd true lift is {(np.exp(lift_prior.tau) - 1) * 100:.1f}% relative")

    calib = time_split_calibration(lifts)
    print(f"[priors] time-split calibration: z-dispersion {calib:.3f} (want ~1.0)")

    payload = {
        "provenance": (
            "Fit ONCE on the exploratory set by analysis/fit_priors.py; frozen thereafter. "
            "Do not refit on confirmatory or holdout data."
        ),
        "ctr_prior": {"a": round(float(ctr_prior.a), 6), "b": round(float(ctr_prior.b), 6)},
        "lift_prior": {
            "mu": round(float(lift_prior.mu), 8),
            "tau2": round(float(lift_prior.tau2), 8),
        },
        "n_lifts_used": len(lifts),
        "time_split_z_dispersion": round(calib, 4),
    }
    with FITTED_PRIORS_PATH.open("w") as f:
        yaml.safe_dump(payload, f, sort_keys=False)
    print(f"[priors] wrote {FITTED_PRIORS_PATH}")


if __name__ == "__main__":
    main()
