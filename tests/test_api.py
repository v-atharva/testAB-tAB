"""Dashboard API contract tests, run against the committed sample results."""

import itertools

import pytest
from fastapi.testclient import TestClient

from dashboard.server import app

client = TestClient(app)


@pytest.fixture(scope="module")
def sample_test_id() -> str:
    r = client.get("/api/tests", params={"dataset": "sample"})
    assert r.status_code == 200
    return str(r.json()[0]["test_id"])


def test_meta() -> None:
    m = client.get("/api/meta").json()
    assert "sample" in m["datasets"]
    assert 0 < m["alpha"] < 1
    assert m["typical_rel_lift"] > 0


def test_readout_contract(sample_test_id: str) -> None:
    r = client.get("/api/readout", params={"dataset": "sample", "test_id": sample_test_id})
    assert r.status_code == 200
    d = r.json()
    assert d["verdict"]["kind"] in {"ship", "keep", "warn", "invalid"}
    assert len(d["arms"]) >= 2
    assert len(d["comparisons"]) == len(d["arms"]) - 1
    assert d["baseline_arm"] == 0
    # P(best) sums to ~1 across arms
    assert sum(a["p_best"] for a in d["arms"]) == pytest.approx(1.0, abs=0.02)


def test_readout_baseline_repick(sample_test_id: str) -> None:
    d = client.get("/api/readout", params={
        "dataset": "sample", "test_id": sample_test_id, "baseline": 1,
    }).json()
    assert d["baseline_arm"] == 1
    assert all(c["arm"] != 1 for c in d["comparisons"])


def test_sequential_replay_is_deterministic(sample_test_id: str) -> None:
    p = {"dataset": "sample", "test_id": sample_test_id, "variant": 1}
    a = client.get("/api/sequential", params=p).json()
    b = client.get("/api/sequential", params=p).json()
    assert a["theta"] == b["theta"]
    assert len(a["frac"]) == len(a["radius"]) == len(a["always_valid_p"])
    # always-valid p is non-increasing
    ps = a["always_valid_p"]
    assert all(x >= y for x, y in itertools.pairwise(ps))


def test_design_calc() -> None:
    d = client.get("/api/design", params={
        "p0": 0.015, "rel": 0.35, "n": 3122, "alpha": 0.05, "power": 0.8,
    }).json()
    assert d["n_needed"] > 3122  # the corpus story: median arm is under-sized
    assert 0 < d["achieved_power_vs_typical"] < 1
    z = d["surface"]["power"]
    assert len(z) == len(d["surface"]["rel_grid"])
    assert len(z[0]) == len(d["surface"]["n_grid"])
    # power increases with n along any lift row
    assert z[-1][-1] >= z[-1][0]


def test_corpus_payload() -> None:
    d = client.get("/api/corpus", params={"dataset": "sample"}).json()
    w = d["winners"]
    assert len(w["naive"]) == len(w["shrunk"]) == len(w["power"]) == len(w["headline"])
    assert len(d["power_hist"]) > 0
    assert sum(d["verdicts"].values()) == 50


def test_unknown_dataset_404() -> None:
    assert client.get("/api/tests", params={"dataset": "nope"}).status_code == 404
