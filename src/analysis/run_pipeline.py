"""Pipeline driver: batch readouts + meta-analysis for one or more datasets.

    python -m analysis.run_pipeline --set exploratory
    python -m analysis.run_pipeline --set sample            # CI smoke run
    python -m analysis.run_pipeline --set confirmatory --set holdout   # ONCE
"""

from __future__ import annotations

import argparse
import json

from analysis.batch_readouts import run_batch
from analysis.config import load_config
from analysis.ingest import load_processed
from analysis.meta import run_meta

VALID_SETS = ("exploratory", "confirmatory", "holdout", "sample")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="append", choices=VALID_SETS, dest="sets",
                        required=True)
    args = parser.parse_args()

    cfg = load_config()
    for name in args.sets:
        print(f"[pipeline] === {name} ===")
        tests, arms = run_batch(name, cfg)
        raw = load_processed(name)
        summary = run_meta(tests, arms, raw, cfg, name)
        print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
