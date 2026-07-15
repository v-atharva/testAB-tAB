"""Load config/defaults.yaml (+ fitted priors) into typed config objects.

The fitted priors are produced ONCE from the exploratory set by
analysis.fit_priors and committed as config/fitted_priors.yaml; every later
stage (batch readouts, dashboard, confirmatory run) treats them as frozen
method parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from abkit.bayes import BetaPrior
from abkit.readout import ReadoutConfig
from abkit.shrinkage import NormalPrior
from analysis.paths import CONFIG_DIR

DEFAULTS_PATH = CONFIG_DIR / "defaults.yaml"
FITTED_PRIORS_PATH = CONFIG_DIR / "fitted_priors.yaml"


@dataclass(frozen=True)
class AppConfig:
    """Everything defaults.yaml declares, plus the frozen fitted priors."""

    readout: ReadoutConfig
    mixture_phi: float
    obf_looks: int
    power_target: float
    replay_seed: int

    @property
    def alpha(self) -> float:
        return self.readout.alpha


def load_defaults(path: Path = DEFAULTS_PATH) -> dict[str, Any]:
    with path.open() as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
    return loaded


def load_fitted_priors(path: Path = FITTED_PRIORS_PATH) -> tuple[NormalPrior, BetaPrior]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Fit corpus priors first (exploratory set only): `make priors`."
        )
    with path.open() as f:
        p: dict[str, Any] = yaml.safe_load(f)
    lift = NormalPrior(mu=float(p["lift_prior"]["mu"]), tau2=float(p["lift_prior"]["tau2"]))
    ctr = BetaPrior(a=float(p["ctr_prior"]["a"]), b=float(p["ctr_prior"]["b"]))
    return lift, ctr


def load_config(
    defaults_path: Path = DEFAULTS_PATH, priors_path: Path = FITTED_PRIORS_PATH
) -> AppConfig:
    d = load_defaults(defaults_path)
    lift_prior, ctr_prior = load_fitted_priors(priors_path)
    readout = ReadoutConfig(
        alpha=float(d["alpha"]),
        srm_alpha=float(d["srm"]["alpha"]),
        min_impressions_per_arm=int(d["gates"]["min_impressions_per_arm"]),
        min_total_impressions=int(d["gates"]["min_total_impressions"]),
        underpowered_below=float(d["gates"]["underpowered_below"]),
        mc_draws=int(d["bayes"]["mc_draws"]),
        seed=int(d["bayes"]["seed"]),
        lift_prior=lift_prior,
        ctr_prior=ctr_prior,
    )
    return AppConfig(
        readout=readout,
        mixture_phi=float(d["sequential"]["mixture_phi"]),
        obf_looks=int(d["sequential"]["obf_looks"]),
        power_target=float(d["power"]["target"]),
        replay_seed=int(d["replay"]["seed"]),
    )
