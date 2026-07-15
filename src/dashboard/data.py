"""Cached data access for the dashboard. Everything here is read-only."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from abkit.readout import ArmCounts, Readout, analyze_experiment
from analysis.config import AppConfig, load_config
from analysis.paths import RESULTS_DIR


@st.cache_resource
def config() -> AppConfig:
    return load_config()


@st.cache_data
def available_datasets() -> list[str]:
    names = [p.name.removesuffix("_tests.parquet") for p in RESULTS_DIR.glob("*_tests.parquet")]
    order = {"exploratory": 0, "confirmatory": 1, "holdout": 2, "sample": 3}
    return sorted(names, key=lambda n: order.get(n, 9))


@st.cache_data
def tests_table(dataset: str) -> pd.DataFrame:
    return pd.read_parquet(RESULTS_DIR / f"{dataset}_tests.parquet")


@st.cache_data
def arms_table(dataset: str) -> pd.DataFrame:
    return pd.read_parquet(RESULTS_DIR / f"{dataset}_arms.parquet")


@st.cache_data
def test_options(dataset: str) -> pd.DataFrame:
    """Picker rows: test_id + a display label built from the baseline headline."""
    arms = arms_table(dataset)
    base = arms[arms["arm_idx"] == 0][["test_id", "headline", "impressions"]]
    tests = tests_table(dataset)[["test_id", "n_arms", "verdict", "total_impressions"]]
    opts = base.merge(tests, on="test_id")
    opts["label"] = (
        opts["headline"].str.slice(0, 80).fillna("(no headline)")
        + "  ·  "
        + opts["n_arms"].astype(str)
        + " arms"
    )
    return opts


def experiment_readout(dataset: str, test_id: str, baseline_idx: int = 0) -> Readout:
    """Live readout for one experiment (~30 ms), honoring a re-picked baseline.

    Counts come from the precomputed arms parquet; statistics are recomputed
    with abkit so the baseline choice is genuinely re-analyzed, not relabeled.
    """
    arms = arms_table(dataset)
    g = arms[arms["test_id"] == test_id].sort_values("arm_idx")
    order = [baseline_idx, *[i for i in g["arm_idx"] if i != baseline_idx]]
    g = g.set_index("arm_idx").loc[order].reset_index()
    counts = [
        ArmCounts(name=f"arm {int(idx)}", impressions=int(imp), clicks=int(clk))
        for idx, imp, clk in zip(
            g["arm_idx"].tolist(), g["impressions"].tolist(), g["clicks"].tolist(),
            strict=True,
        )
    ]
    return analyze_experiment(counts, config().readout)


def experiment_arms(dataset: str, test_id: str) -> pd.DataFrame:
    arms = arms_table(dataset)
    return arms[arms["test_id"] == test_id].sort_values("arm_idx").reset_index(drop=True)
