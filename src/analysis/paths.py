"""Canonical repo-relative paths for the pipeline."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"
DATA_SAMPLE = REPO_ROOT / "data" / "sample"
RESULTS_DIR = REPO_ROOT / "outputs" / "results"
FIGURES_DIR = REPO_ROOT / "outputs" / "figures"
