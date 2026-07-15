"""Build the bundled 50-test CI sample from the raw exploratory CSV.

The sample keeps the RAW archive schema so the smoke run exercises the exact
same normalize/validate path as the real datasets. Selection is deterministic
(seeded) but stratified to cover the interesting cases: 2-arm and many-arm
tests, at least one test with an Upworthy-declared winner, and at least one
zero-click arm.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.paths import DATA_RAW, DATA_SAMPLE

SEED = 20260715
N_TESTS = 50


def main() -> None:
    raw_path = DATA_RAW / "exploratory.csv"
    if not raw_path.exists():
        raise FileNotFoundError("run `python -m analysis.ingest --set exploratory` first")
    df = pd.read_csv(raw_path, index_col=0)
    rng = np.random.default_rng(SEED)

    by_test = df.groupby("clickability_test_id")
    sizes = by_test.size()
    has_winner = by_test["winner"].any()
    has_zero_click = by_test["clicks"].min() == 0

    chosen: set[str] = set()

    def take(pool: pd.Index, n: int) -> None:
        pool = pool.difference(list(chosen))
        picks = rng.choice(pool.to_numpy(), size=min(n, len(pool)), replace=False)
        chosen.update(str(p) for p in picks)

    take(sizes[sizes == 2].index, 5)  # rare 2-arm tests
    take(sizes[sizes >= 6].index, 5)  # many-arm tests
    take(has_winner[has_winner].index, 5)  # Upworthy declared a winner
    take(has_zero_click[has_zero_click].index, 2)  # zero-click arm edge case
    take(sizes.index, N_TESTS - len(chosen))  # fill with typical tests

    sample = df[df["clickability_test_id"].isin(chosen)]
    DATA_SAMPLE.mkdir(parents=True, exist_ok=True)
    dest = DATA_SAMPLE / "sample_50_tests.csv"
    sample.to_csv(dest)
    print(
        f"[sample] wrote {sample['clickability_test_id'].nunique()} tests / "
        f"{len(sample)} arms -> {dest}"
    )


if __name__ == "__main__":
    main()
