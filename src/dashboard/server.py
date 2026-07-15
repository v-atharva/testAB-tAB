"""Dashboard server: a thin, read-only JSON API over abkit + batch results,
plus the static single-page frontend in src/dashboard/web/.

Run: `make dashboard` (uvicorn dashboard.server:app). Every statistic served
here is computed by abkit or read from the precomputed parquet — the frontend
renders numbers, it never derives them.
"""

from __future__ import annotations

import math
import zlib
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from abkit import design, sequential
from abkit.readout import Readout, Verdict
from dashboard import data

app = FastAPI(title="Upworthy readout API", docs_url="/api/docs", openapi_url="/api/openapi.json")

WEB_DIR = Path(__file__).resolve().parent / "web"
N_LOOKS = 60

VERDICT_KIND = {
    Verdict.SHIP_VARIANT: "ship",
    Verdict.KEEP_BASELINE: "keep",
    Verdict.UNDERPOWERED: "warn",
    Verdict.INSUFFICIENT_DATA: "warn",
    Verdict.INVALID_SRM: "invalid",
}


def _f(x: float | None, nd: int = 6) -> float | None:
    """JSON-safe float (NaN -> None), rounded to keep payloads compact."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    return round(float(x), nd)


def _dataset_or_404(dataset: str) -> str:
    if dataset not in data.available_datasets():
        raise HTTPException(404, f"unknown dataset {dataset!r}")
    return dataset


# --------------------------------------------------------------------- meta


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    cfg = data.config()
    prior = cfg.readout.lift_prior
    return {
        "datasets": list(data.available_datasets()),
        "alpha": cfg.readout.alpha,
        "ctr_prior_mean": _f(cfg.readout.ctr_prior.mean),
        "typical_rel_lift": _f(math.exp(prior.tau) - 1, 4),
        "median_arm_impressions": 3122,  # exploratory median, see README
    }


# -------------------------------------------------------------------- tests


@app.get("/api/tests")
def tests(dataset: str = Query(...)) -> list[dict[str, Any]]:
    _dataset_or_404(dataset)
    arms = data.arms_table(dataset)
    base = arms[arms["arm_idx"] == 0][["test_id", "headline"]]
    t = data.tests_table(dataset)[["test_id", "n_arms", "verdict", "total_impressions"]]
    merged = base.merge(t, on="test_id")
    return [
        {
            "test_id": tid,
            "headline": (str(hl) or "(no headline)")[:110],
            "n_arms": int(na),
            "verdict": str(v),
            "impressions": int(imp),
        }
        for tid, hl, na, v, imp in zip(
            merged["test_id"].tolist(), merged["headline"].tolist(),
            merged["n_arms"].tolist(), merged["verdict"].tolist(),
            merged["total_impressions"].tolist(), strict=True,
        )
    ]


# ------------------------------------------------------------------ readout


def _serialize_readout(
    r: Readout, arm_order: list[int], headlines: dict[int, str]
) -> dict[str, Any]:
    return {
        "verdict": {
            "kind": VERDICT_KIND[r.verdict],
            "code": r.verdict.value,
            "headline": r.headline,
            "notes": list(r.notes),
        },
        "health": {
            "srm_p": _f(r.srm.p_value),
            "srm_failed": r.srm.failed,
            "gated": r.quality.gated,
            "gate_reasons": list(r.quality.reasons),
            "zero_click_arms": [arm_order[i] for i in r.quality.zero_click_arms],
            "achieved_power": _f(r.achieved_power, 4),
            "benchmark_rel_lift": _f(r.benchmark_rel_lift, 4),
        },
        "omnibus_p": _f(r.omnibus_chi2_p),
        "baseline_arm": arm_order[0],
        "best_arm": arm_order[r.best_arm_index],
        "arms": [
            {
                "arm": arm_order[i],
                "headline": headlines.get(arm_order[i], ""),
                "impressions": a.impressions,
                "clicks": a.clicks,
                "ctr": _f(a.ctr),
                "ctr_lo": _f(a.ctr_ci.lo),
                "ctr_hi": _f(a.ctr_ci.hi),
                "p_best": _f(a.p_best, 4),
                "expected_loss": _f(a.expected_loss, 7),
            }
            for i, a in enumerate(r.arms)
        ],
        "comparisons": [
            {
                "arm": arm_order[c.arm_index],
                "raw_p": _f(c.z_p_value),
                "holm_p": _f(c.holm_p_value),
                "abs_lift": _f(c.abs_lift),
                "abs_lo": _f(c.abs_lift_ci.lo),
                "abs_hi": _f(c.abs_lift_ci.hi),
                "rel_lift": _f(c.rel_lift, 4),
                "rel_lo": _f(c.rel_lift_ci.lo, 4) if c.rel_lift_ci else None,
                "rel_hi": _f(c.rel_lift_ci.hi, 4) if c.rel_lift_ci else None,
                "shrunk_rel": _f(c.shrunk_rel_lift, 4),
                "shrunk_lo": _f(c.shrunk_rel_ci[0], 4) if c.shrunk_rel_ci else None,
                "shrunk_hi": _f(c.shrunk_rel_ci[1], 4) if c.shrunk_rel_ci else None,
                "significant": c.significant,
            }
            for c in r.comparisons
        ],
    }


@app.get("/api/readout")
def readout(
    dataset: str = Query(...), test_id: str = Query(...), baseline: int = Query(0)
) -> dict[str, Any]:
    _dataset_or_404(dataset)
    try:
        g = data.experiment_arms(dataset, test_id)
        r = data.experiment_readout(dataset, test_id, baseline)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    order = [baseline, *[int(i) for i in g["arm_idx"] if i != baseline]]
    headlines = {int(i): str(h)[:200] for i, h in zip(g["arm_idx"], g["headline"], strict=True)}
    return _serialize_readout(r, order, headlines)


# ---------------------------------------------------------------- sequential


@app.get("/api/sequential")
def sequential_replay(
    dataset: str = Query(...), test_id: str = Query(...), variant: int = Query(1)
) -> dict[str, Any]:
    _dataset_or_404(dataset)
    try:
        g = data.experiment_arms(dataset, test_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    if variant not in set(g["arm_idx"]) or variant == 0:
        raise HTTPException(404, f"variant arm {variant} not available")
    cfg = data.config()
    base = g[g["arm_idx"] == 0].iloc[0]
    var = g[g["arm_idx"] == variant].iloc[0]

    seed = cfg.replay_seed ^ zlib.crc32(f"{test_id}/{variant}".encode())
    rng = np.random.default_rng(seed)
    k1 = sequential.conditional_permutation_replay(
        int(var["clicks"]), int(var["impressions"]), N_LOOKS, rng)
    k0 = sequential.conditional_permutation_replay(
        int(base["clicks"]), int(base["impressions"]), N_LOOKS, rng)
    n1 = sequential.replay_looks(int(var["impressions"]), N_LOOKS)
    n0 = sequential.replay_looks(int(base["impressions"]), N_LOOKS)

    trace = sequential.msprt_two_prop(k1, n1, k0, n0, phi=cfg.mixture_phi, alpha=cfg.alpha)
    naive_first = sequential.naive_peeking_rejections(k1, n1, k0, n0, cfg.alpha)

    from scipy import stats as sps

    pooled = (k1 + k0) / (n1 + n0)
    v = pooled * (1 - pooled) * (1 / n1 + 1 / n0)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(v > 0, (k1 / n1 - k0 / n0) / np.sqrt(v), 0.0)
    naive_sig = (2 * sps.norm.sf(np.abs(z)) < cfg.alpha).tolist()

    frac = ((n1 + n0) / (n1[-1] + n0[-1])).tolist()
    return {
        "frac": [round(x, 5) for x in frac],
        "theta": [_f(x) for x in trace.theta_hat],
        "radius": [_f(min(x, 1.0)) for x in trace.cs_radius],
        "always_valid_p": [_f(x, 5) for x in trace.always_valid_p],
        "naive_sig": naive_sig,
        "first_rejection": trace.first_rejection,
        "naive_first": naive_first,
        "variant_headline": str(var["headline"])[:160],
        "baseline_headline": str(base["headline"])[:160],
    }


# -------------------------------------------------------------------- design


@app.get("/api/design")
def design_calc(
    p0: float = Query(..., gt=0.0, lt=1.0),
    rel: float = Query(..., gt=0.0, le=3.0),
    n: int = Query(..., ge=10, le=50_000_000),
    alpha: float = Query(0.05, gt=0.0, lt=0.5),
    power: float = Query(0.80, gt=0.5, lt=1.0),
) -> dict[str, Any]:
    cfg = data.config()
    typical = math.exp(cfg.readout.lift_prior.tau) - 1
    p1 = min(1 - 1e-9, p0 * (1 + rel))
    n_needed = design.sample_size_two_prop(p0, p1, alpha=alpha, power=power)
    mde_abs = design.mde_two_prop(p0, n, alpha=alpha, power=power)
    achieved = design.power_two_prop(p0, min(1 - 1e-9, p0 * (1 + typical)), n, alpha)

    # 3-D power surface: impressions per arm x relative lift -> power
    n_grid = np.unique(np.geomspace(200, max(200_000, n * 2), 28).astype(int))
    rel_grid = np.linspace(0.02, max(1.0, rel * 1.2), 26)
    surface = [
        [
            _f(design.power_two_prop(p0, min(1 - 1e-9, p0 * (1 + r)), int(m), alpha), 4)
            for m in n_grid
        ]
        for r in rel_grid
    ]
    return {
        "n_needed": n_needed,
        "mde_rel": _f(mde_abs / p0, 4),
        "mde_abs": _f(mde_abs),
        "achieved_power_vs_typical": _f(achieved, 4),
        "typical_rel_lift": _f(typical, 4),
        "surface": {
            "n_grid": n_grid.tolist(),
            "rel_grid": [_f(r, 4) for r in rel_grid],
            "power": surface,
        },
    }


# -------------------------------------------------------------------- corpus


@app.get("/api/corpus")
def corpus(dataset: str = Query(...)) -> dict[str, Any]:
    import json

    from analysis.paths import RESULTS_DIR

    _dataset_or_404(dataset)
    t = data.tests_table(dataset)
    arms = data.arms_table(dataset)
    summary_path = RESULTS_DIR / f"{dataset}_summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}

    win = t[t["sig_corrected"] & t["winner_rel_lift_naive"].notna()
            & t["winner_rel_lift_shrunk"].notna()]
    base_hl = arms[arms["arm_idx"] == 0].set_index("test_id")["headline"]
    hl = win["test_id"].map(base_hl).fillna("").str.slice(0, 80)

    ok = t[~t["srm_failed"]]
    return {
        "summary": summary,
        "winners": {
            "naive": [_f(x, 4) for x in win["winner_rel_lift_naive"]],
            "shrunk": [_f(x, 4) for x in win["winner_rel_lift_shrunk"]],
            "power": [_f(x, 4) for x in win["achieved_power"]],
            "headline": hl.tolist(),
        },
        "power_hist": [_f(x, 4) for x in ok["achieved_power"]],
        "verdicts": t["verdict"].value_counts().to_dict(),
    }


# -------------------------------------------------------------------- static


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
