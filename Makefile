# Every artifact in this project is regenerable from here.
.PHONY: setup lint test test-fast data sample priors analysis smoke figures dashboard confirmatory

# Belt and suspenders: on macOS, iCloud Desktop sync intermittently marks the
# editable-install .pth "hidden", which Python 3.13 then skips. PYTHONPATH keeps
# `python -m analysis...` working regardless; `make setup` clears the flag too.
export PYTHONPATH := src

setup:  ## install the environment (uv) and de-hide editable .pth (macOS/iCloud quirk)
	uv sync
	-chflags nohidden .venv/lib/python*/site-packages/*.pth 2>/dev/null

lint:
	uv run ruff check src tests
	uv run mypy

test:
	uv run pytest tests/

test-fast:
	uv run pytest tests/ -m "not slow"

data:  ## download the archive from OSF (checksummed, cached in data/raw/)
	uv run python -m analysis.ingest --all

sample:  ## rebuild the bundled 50-test CI sample from the exploratory set
	uv run python -m analysis.ingest --set exploratory
	uv run python -m analysis.make_sample

priors:  ## fit corpus priors on the EXPLORATORY set only (writes config/fitted_priors.yaml)
	uv run python -m analysis.fit_priors

analysis:  ## batch readouts + meta-analysis + figures on the exploratory set
	uv run python -m analysis.run_pipeline --set exploratory

smoke:  ## end-to-end pipeline on the bundled sample (what CI runs; no downloads)
	uv run python -m analysis.run_pipeline --set sample

confirmatory:  ## the one-shot final run (confirmatory + holdout). Run ONCE.
	uv run python -m analysis.ingest --set confirmatory --set holdout
	uv run python -m analysis.run_pipeline --set confirmatory --set holdout

figures: analysis

dashboard:
	uv run streamlit run src/dashboard/app.py
