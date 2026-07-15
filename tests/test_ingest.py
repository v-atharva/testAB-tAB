"""Ingest/normalize contract, exercised on the committed 50-test sample."""

import pandas as pd
import pytest

from analysis import ingest


@pytest.fixture(scope="module")
def sample() -> pd.DataFrame:
    return ingest.load_processed("sample")


def test_sample_shape(sample: pd.DataFrame) -> None:
    assert sample["test_id"].nunique() == 50
    assert set(sample.columns) >= {
        "test_id",
        "arm_idx",
        "impressions",
        "clicks",
        "headline",
        "created_at",
        "upworthy_winner",
    }


def test_counts_are_sane(sample: pd.DataFrame) -> None:
    assert (sample["impressions"] > 0).all()
    assert (sample["clicks"] >= 0).all()
    assert (sample["clicks"] <= sample["impressions"]).all()


def test_arm_zero_is_earliest_created(sample: pd.DataFrame) -> None:
    """The baseline convention: arm_idx orders by created_at within test."""
    for _, g in sample.groupby("test_id"):
        g = g.sort_values("arm_idx")
        assert list(g["arm_idx"]) == list(range(len(g)))
        assert g["created_at"].is_monotonic_increasing


def test_sample_covers_edge_cases(sample: pd.DataFrame) -> None:
    sizes = sample.groupby("test_id").size()
    assert (sizes == 2).any(), "sample should include a 2-arm test"
    assert (sizes >= 6).any(), "sample should include a many-arm test"
    assert sample.groupby("test_id")["upworthy_winner"].any().any()
    assert (sample.groupby("test_id")["clicks"].min() == 0).any()


def test_every_test_has_at_least_two_arms(sample: pd.DataFrame) -> None:
    assert (sample.groupby("test_id").size() >= 2).all()
