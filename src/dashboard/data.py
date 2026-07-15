"""Read-only data access for the dashboard API.

Pure Python (no web framework imports): parquet reads are cached per process,
single-experiment readouts are recomputed live with abkit (~30 ms) so a
re-picked baseline is genuinely re-analyzed, never relabeled.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from abkit.readout import ArmCounts, Readout, analyze_experiment
from analysis.config import AppConfig, load_config
from analysis.paths import RESULTS_DIR


@lru_cache(maxsize=1)
def config() -> AppConfig:
    return load_config()


@lru_cache(maxsize=1)
def available_datasets() -> tuple[str, ...]:
    names = [p.name.removesuffix("_tests.parquet") for p in RESULTS_DIR.glob("*_tests.parquet")]
    order = {"exploratory": 0, "confirmatory": 1, "holdout": 2, "sample": 3}
    return tuple(sorted(names, key=lambda n: order.get(n, 9)))


@lru_cache(maxsize=8)
def tests_table(dataset: str) -> pd.DataFrame:
    return pd.read_parquet(RESULTS_DIR / f"{dataset}_tests.parquet")


@lru_cache(maxsize=8)
def arms_table(dataset: str) -> pd.DataFrame:
    return pd.read_parquet(RESULTS_DIR / f"{dataset}_arms.parquet")


def experiment_arms(dataset: str, test_id: str) -> pd.DataFrame:
    arms = arms_table(dataset)
    g = arms[arms["test_id"] == test_id]
    if g.empty:
        raise KeyError(f"unknown test_id {test_id!r} in {dataset}")
    return g.sort_values("arm_idx").reset_index(drop=True)


def experiment_readout(dataset: str, test_id: str, baseline_idx: int = 0) -> Readout:
    """Live readout for one experiment, honoring a re-picked baseline arm."""
    g = experiment_arms(dataset, test_id)
    if baseline_idx not in set(g["arm_idx"]):
        raise KeyError(f"arm {baseline_idx} does not exist in test {test_id!r}")
    order = [baseline_idx, *[int(i) for i in g["arm_idx"] if i != baseline_idx]]
    g = g.set_index("arm_idx").loc[order].reset_index()
    counts = [
        ArmCounts(name=f"arm {int(idx)}", impressions=int(imp), clicks=int(clk))
        for idx, imp, clk in zip(
            g["arm_idx"].tolist(), g["impressions"].tolist(), g["clicks"].tolist(),
            strict=True,
        )
    ]
    return analyze_experiment(counts, config().readout)
