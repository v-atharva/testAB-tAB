# 32,487 real A/B tests: an experiment readout engine and decision dashboard

Every headline/image A/B test Upworthy.com ran between January 2013 and April
2015 — 32,487 experiments, 150,817 arms, ~538 million participant assignments
([Upworthy Research Archive](https://upworthy.natematias.com/about-the-archive.html),
[Nature Scientific Data](https://www.nature.com/articles/s41597-021-00934-7)) —
re-analyzed with the statistics an experimentation platform should have applied,
and a dashboard that renders a decision-grade readout for any of them.

**What an experiment readout must get right:** health checks before inference
(a broken traffic split invalidates a test, it doesn't decide it); corrections
for testing many arms and many experiments; the winner's curse (the arm you
noticed *because it won* is exaggerated by selection); power against effects
that actually occur, so "not significant" is never silently read as "no
effect"; and anytime-valid methods if anyone will peek before the end. This
repo demonstrates all five, on real data, at scale.

<p align="center"><img src="outputs/figures/dashboard/readout_page.png" width="85%"></p>

## Headline findings (confirmatory + holdout, run once)

27,612 tests (22,741 confirmatory + 4,871 holdout; 2 single-arm tests dropped),
analyzed once with methods frozen from the exploratory set:

| # | Finding | Number |
|---|---------|--------|
| 1 | **Winner's curse is huge.** The median winning arm claims **+96%** relative CTR lift; the shrinkage-corrected estimate is **+50%** — a median exaggeration of **×1.69**. Selection bias grows as power falls (see figure). | ×1.69 |
| 2 | **Most "wins" evaporate under honest accounting.** 5,009 tests have an uncorrected significant winner → 3,197 survive within-test Holm → 1,554 survive corpus-level BH. | **69% evaporate** |
| 3 | **The corpus was underpowered for its own effect sizes.** Median power to detect a corpus-typical lift (+35% relative): **32%**. Tests reaching the 80% planning bar: **3.5%**. Verdicts: 55.8% "underpowered — don't conclude", 17.1% keep baseline, 11.6% ship a variant. | 3.5% adequately powered |
| 4 | **Peeking would have wrecked it.** Stop-at-first-p<0.05 hits a 22–27% false-positive rate at 20–50 looks on null streams (mSPRT: ≤0.5% monitored continuously). Replaying real no-winner tests, naive peeking shows a phantom mid-test "win" in **38%** of them. | 27% vs 0.5% FP |
| 5 | **15.4% of tests fail SRM** (traffic split inconsistent with uniform randomization at p<0.001, ~150× the nominal rate) and are excluded from every count above. | 4,259 tests |
| 6 | **Upworthy's own declared winners rarely survive.** Of 6,502 tests where their tooling declared a winner, **19.9%** are confirmed by the corrected analysis; 51% were declared from underpowered tests. | 1 in 5 confirmed |

Every one of these replicated out-of-sample: exploratory → confirmatory →
holdout give exaggeration ×1.65 / ×1.69 / ×1.73, evaporation 70% / 69% / 68%,
median power 32% in all three, SRM 15.5% / 15.5% / 15.0%. Per-set numbers:
`outputs/results/{set}_summary.json`.

<p align="center"><img src="outputs/figures/confirmatory/winners_curse.png" width="90%"></p>

The exploratory/confirmatory discipline is itself part of the demonstration:
the archive ships pre-split, and **every method, threshold, prior, and default
here was developed on the exploratory set only** (4,873 tests). The
confirmatory + holdout sets (27,614 tests) were analyzed exactly once, with
methods frozen, to produce the numbers above. No result from those sets fed
back into any choice.

## The three components

### 1. `abkit` — a reusable experimentation library (`src/abkit/`)

Pure typed functions on counts; no I/O. Design (power / MDE / sample size),
frequentist readout (two-proportion z, Wilson & Newcombe & Katz intervals,
k-arm chi-square), sequential inference (mSPRT always-valid p-values and
confidence sequences; Monte-Carlo-calibrated O'Brien–Fleming boundaries for
contrast), multiplicity (Holm within a test, Benjamini-Hochberg across a
corpus), empirical-Bayes shrinkage with winner's-curse estimators,
Beta-Binomial Bayesian readout (P(best), expected loss), and health checks
(SRM, minimum-sample gates) — composed into one verdict by `abkit.readout`.

**Every statistical routine is validated in `tests/` against simulation or a
reference implementation**: empirical type-I error ≈ α, CI coverage ≈ nominal,
shrinkage posterior calibration, mSPRT error control under *continuous*
monitoring (while the naive repeated z-test demonstrably inflates), and
O'Brien–Fleming constants recovered against published values.

### 2. Corpus meta-analysis (`src/analysis/`)

Checksummed OSF ingest → count validation against the published totals →
corpus priors fit on the exploratory set (frozen thereafter) → batch readouts
→ the figures in `outputs/figures/` and the numbers above.

### 3. Decision dashboard (`src/dashboard/`, Streamlit)

A readout tool, not a chart gallery. Four screens: **experiment readout**
(verdict → naive *vs* corrected lift with intervals → Bayesian panel → health
badges → achieved power, every number with a plain-English line a PM can act
on), **sequential monitoring** (replay a test with a narrowing confidence
sequence, a "could have safely stopped here" marker, and the naive peeking
rejections it avoids), **design-a-test** (power/MDE anchored to the corpus
prior: *plan for lifts that actually occur*), and the **corpus explorer**.
Read-only over precomputed parquet; an uncorrected significant result is never
presented as a win anywhere in the UI.

## Run it

```bash
make setup       # uv sync (Python 3.11+)
make dashboard   # committed batch results make this work immediately
```

Full reproduction:

```bash
make data        # checksummed downloads from OSF (~95 MB)
make priors      # refit corpus priors (exploratory only)
make analysis    # exploratory batch + figures
make test        # 82 tests incl. the simulation-validation suite
make confirmatory  # the one-shot final run — intentionally not idempotent in spirit
```

Docker: `docker build -t upworthy-readout . && docker run -p 8501:8501 upworthy-readout`.
CI runs lint (ruff), types (mypy strict), the full test suite, and an
end-to-end pipeline smoke run on a committed 50-test sample — it never
downloads the archive.

## Methods appendix

- **Baseline convention.** The archive designates no control arm; the
  earliest-created package is treated as the incumbent baseline (stated in the
  UI, re-pickable in the dashboard). Only 2.6% of tests are 2-arm; the modal
  test has 4 arms, so k-arm corrections are the norm, not an edge case.
- **Intervals.** Wilson per arm; Newcombe hybrid for absolute lift; Katz
  log-scale for relative lift. At 1.5% CTR, Wald intervals are unreliable and
  are not used. Zero-click arms are legal inputs: the relative lift is
  reported as *undefined* there, never as a number.
- **Shrinkage.** theta = log-odds lift vs baseline; theta_hat ~ N(theta, se²)
  with Woolf variance; theta ~ N(mu, tau²) fit by marginal MLE on exploratory
  (mu = −0.064: later-created variants run slightly worse than the incumbent
  on average; tau = 0.303: a one-sd true lift is ~35% relative — headline
  effects at Upworthy were large and heterogeneous). Time-split calibration
  (fit early weeks, score late weeks) gives z-dispersion 1.06 ≈ 1. Posterior
  means are the "corrected" lifts everywhere. Odds-ratio ≈ risk-ratio at these
  CTRs (documented approximation).
- **Sequential.** mSPRT with a normal mixture on the absolute lift; mixture
  variance phi = 2.5e-5 ≈ E[theta²] under the corpus prior (validity holds for
  any phi; only power depends on it). Confidence sequences from the same
  martingale. No event-level data exists, so dashboard replays are
  **conditional permutation replays** — exact given the final counts, labeled
  as reconstructions. Corpus peeking-damage numbers come from simulated
  streams with known truth.
- **Multiplicity.** Holm across a test's pairwise-vs-baseline comparisons
  (family-wise control for "ship X"); BH at q=0.05 across the corpus on the
  per-test Holm-corrected p (FDR control for "how many wins are there").
- **SRM.** Chi-square against uniform allocation at α=1e-3. A large share of
  archive tests fail (15.5% exploratory). We checked the obvious mechanism —
  arms added mid-test — and it does *not* explain the failures (failing tests
  have *smaller* arm-creation spreads). The cause is not recoverable from
  aggregate data; flagged tests are excluded from all win counts, which is the
  correct platform behavior regardless of mechanism.
- **Power.** "Achieved power" is against a one-prior-sd true lift — the size
  of effect this corpus actually produces — not an arbitrary MDE.
- **Every default** (α=0.05, SRM α=1e-3, gates, phi, MC draws, seeds) lives in
  `config/defaults.yaml`; the fitted priors in `config/fitted_priors.yaml`
  with provenance.

## Limitations

- **One metric.** Clicks/impressions only. No downstream engagement, no
  guardrails; a real decision would weigh more than CTR.
- **2013–15 media context.** Upworthy-era curiosity-gap headlines; effect
  sizes and feature findings should not be extrapolated to other products or
  eras.
- **No user-level data.** Aggregates per arm only: no CUPED (nothing to
  covary on), no interference or novelty-effect checks, and sequential replays
  are reconstructions, not logs.
- **SRM mechanism unknown.** We can flag and exclude, but not diagnose, the
  allocation anomalies.
- **External validity.** One company, one surface, one outcome. The *methods*
  transfer; the *numbers* describe this corpus.

## What I'd add inside a real experimentation platform

- **Guardrail metrics with non-inferiority gates** — a CTR win that hurts
  retention or revenue is a loss; verdicts should require "primary wins AND
  guardrails don't regress (one-sided non-inferiority)".
- **CUPED / regression adjustment** on user-level pre-exposure covariates —
  the standard 30–50% variance cut this archive can't demonstrate for lack of
  user data.
- **Automated SRM triage**, not just detection: segment-level chi-squares
  (browser, geo, day) to localize the broken slice, and quarantine rules.
- **Interference & novelty checks** — switchback or cluster designs where
  units interact; first-week vs later-week effect comparison before shipping.
- **Corpus-level holdouts** — a standing 5% global holdout to measure the
  *cumulative* effect of shipped wins against the shrinkage predictions (the
  winner's-curse ledger, closed).
- **Decision memos as artifacts** — the dashboard's verdict block, persisted
  and versioned per experiment, so "why did we ship this" has an answer a year
  later.

## Repo map

```
src/abkit/        the library (typed, tested, importable on its own)
src/analysis/     ingest → priors → batch readouts → meta-analysis figures
src/dashboard/    Streamlit app (4 pages, read-only)
config/           every default + frozen fitted priors
data/sample/      committed 50-test sample (CI smoke runs; raw schema)
notebooks/        one narrative notebook (executes cleanly end-to-end)
outputs/          figures + committed batch results
tests/            82 tests; the simulation-validation suite is the point
```

Data: Upworthy Research Archive, courtesy of Good Inc. and the archive team
(Matias, Munger, et al.). Distributed for research via
[OSF](https://osf.io/jd64p/).
