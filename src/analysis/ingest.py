"""Download, validate, and normalize the Upworthy Research Archive.

Sources are the official OSF distribution (node jd64p). Downloads are cached
in data/raw/ and verified against pinned SHA-256 checksums; parsed datasets
are validated against the published package/test counts before anything else
is allowed to touch them.

Usage:
    python -m analysis.ingest --set exploratory [--set confirmatory ...]
    python -m analysis.ingest --all
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

from analysis.paths import DATA_PROCESSED, DATA_RAW, DATA_SAMPLE


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    url: str
    sha256: str
    expected_packages: int
    expected_tests: int


# Verified 2026-07-15 against the OSF listing and the archive paper
# (Matias, Munger et al., Nature Scientific Data 2021).
DATASETS: dict[str, DatasetSpec] = {
    "exploratory": DatasetSpec(
        name="exploratory",
        url="https://osf.io/download/3vqmp/",
        sha256="8368313b060f4015a0c6fb34e6d788163cee29554144aba9390b14922eb9d8ce",
        expected_packages=22_666,
        expected_tests=4_873,
    ),
    "confirmatory": DatasetSpec(
        name="confirmatory",
        url="https://osf.io/download/vy8mj/",
        sha256="b2a88288c88f2b67d40413c9bdbebe79a1c0b5d9a9354180549f59f3bfff685f",
        expected_packages=105_551,
        expected_tests=22_743,
    ),
    "holdout": DatasetSpec(
        name="holdout",
        url="https://osf.io/download/ynf3k/",
        sha256="93832660b831aca16bbe314c60dba4a6815b0a5f9cdded1217671cfbfa5186ea",
        expected_packages=22_600,
        expected_tests=4_871,
    ),
}

RAW_COLUMNS = [
    "created_at",
    "updated_at",
    "clickability_test_id",
    "excerpt",
    "headline",
    "lede",
    "slug",
    "eyecatcher_id",
    "impressions",
    "clicks",
    "significance",
    "first_place",
    "winner",
    "share_text",
    "square",
    "test_week",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(spec: DatasetSpec, force: bool = False) -> Path:
    """Fetch one dataset into data/raw/, verifying the pinned checksum."""
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    dest = DATA_RAW / f"{spec.name}.csv"
    if dest.exists() and not force:
        digest = _sha256(dest)
        if digest == spec.sha256:
            print(f"[ingest] {spec.name}: cached and checksum-verified")
            return dest
        print(f"[ingest] {spec.name}: cached file has wrong checksum, re-downloading")
    print(f"[ingest] {spec.name}: downloading from {spec.url}")
    with requests.get(spec.url, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(".part")
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    digest = _sha256(tmp)
    if digest != spec.sha256:
        tmp.unlink()
        raise RuntimeError(
            f"{spec.name}: downloaded file checksum {digest} does not match pinned "
            f"{spec.sha256} — the OSF file may have changed; do not proceed silently."
        )
    tmp.rename(dest)
    print(f"[ingest] {spec.name}: downloaded and checksum-verified")
    return dest


def normalize(raw_csv: Path, spec: DatasetSpec | None = None) -> pd.DataFrame:
    """Parse a raw archive CSV into the analysis schema.

    One row per arm ("package"), with `arm_idx` ordered by created_at within
    each test — arm 0 is the earliest-created package, the project's baseline
    convention. Upworthy's own readout columns are kept under upworthy_*.
    Single-arm tests (present in principle, none in the exploratory set) are
    dropped with a notice: no within-test comparison exists for them.
    """
    df = pd.read_csv(raw_csv, index_col=0, low_memory=False)
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{raw_csv}: unexpected schema, missing columns {missing}")

    if spec is not None:
        if len(df) != spec.expected_packages:
            raise ValueError(
                f"{spec.name}: {len(df)} packages, expected {spec.expected_packages}"
            )
        n_tests = df["clickability_test_id"].nunique()
        if n_tests != spec.expected_tests:
            raise ValueError(f"{spec.name}: {n_tests} tests, expected {spec.expected_tests}")

    out = pd.DataFrame(
        {
            "test_id": df["clickability_test_id"].astype("string"),
            "created_at": pd.to_datetime(df["created_at"], format="mixed"),
            "impressions": df["impressions"].astype("int64"),
            "clicks": df["clicks"].astype("int64"),
            "headline": df["headline"].fillna("").astype("string"),
            "eyecatcher_id": df["eyecatcher_id"].fillna("").astype("string"),
            "share_text": df["share_text"].fillna("").astype("string"),
            "lede": df["lede"].fillna("").astype("string"),
            "excerpt": df["excerpt"].fillna("").astype("string"),
            "slug": df["slug"].fillna("").astype("string"),
            "test_week": df["test_week"].astype("int64"),
            "upworthy_significance": pd.to_numeric(df["significance"], errors="coerce"),
            "upworthy_first_place": df["first_place"].astype("boolean").fillna(False),
            "upworthy_winner": df["winner"].astype("boolean").fillna(False),
        }
    )

    if (out["impressions"] <= 0).any():
        raise ValueError("found arms with non-positive impressions")
    if ((out["clicks"] < 0) | (out["clicks"] > out["impressions"])).any():
        raise ValueError("found arms with clicks outside [0, impressions]")

    out = out.sort_values(["test_id", "created_at"], kind="stable").reset_index(drop=True)
    out["arm_idx"] = out.groupby("test_id").cumcount()

    arm_counts = out.groupby("test_id")["arm_idx"].transform("size")
    single = int((arm_counts == 1).sum())
    if single:
        print(f"[ingest] dropping {single} single-arm test(s): nothing to compare within them")
        out = out[arm_counts > 1].reset_index(drop=True)
    return out


def load_processed(name: str) -> pd.DataFrame:
    """Read a normalized dataset ('exploratory', 'confirmatory', 'holdout', 'sample')."""
    if name == "sample":
        path = DATA_SAMPLE / "sample_50_tests.csv"
        if not path.exists():
            raise FileNotFoundError(f"bundled sample missing at {path} (should be committed)")
        return normalize(path)
    path = DATA_PROCESSED / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `python -m analysis.ingest --set {name}`")
    return pd.read_parquet(path)


def ingest(name: str, force: bool = False) -> Path:
    spec = DATASETS[name]
    raw = download(spec, force=force)
    df = normalize(raw, spec)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    dest = DATA_PROCESSED / f"{name}.parquet"
    df.to_parquet(dest, index=False)
    print(
        f"[ingest] {name}: normalized {df['test_id'].nunique()} tests / {len(df)} arms -> {dest}"
    )
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="append", choices=sorted(DATASETS), dest="sets")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()
    names = sorted(DATASETS) if args.all else args.sets
    if not names:
        parser.error("pass --set <name> (repeatable) or --all")
        sys.exit(2)
    for name in names:
        ingest(name, force=args.force)


if __name__ == "__main__":
    main()
