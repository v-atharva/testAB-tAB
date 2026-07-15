# PLAN

The plan this project was built against, recorded before implementation.
(Original working plan written 2026-07-15, after downloading and inspecting the
exploratory dataset; kept here in distilled form as part of the audit trail.)

## Verified facts encoded up front

- OSF distribution (node `jd64p`), three files, SHA-256s pinned in
  `src/analysis/ingest.py`: exploratory (4,873 tests / 22,666 packages),
  confirmatory (22,743 / 105,551), holdout (4,871 / 22,600) = 32,487 tests,
  150,817 packages, ~538M assignments.
- Identical 17-column schema across files; includes Upworthy's own readout
  columns (`significance`, `first_place`, `winner`) — audited, never reused.
- Only 2.6% of exploratory tests have 2 arms (mode: 4). No designated control.
- Median arm ~3,122 impressions at ~1.5% CTR (~47 clicks); min 13 impressions;
  12 zero-click arms; per-package timestamps only (no event-level data).

## Decisions made before any pipeline code

1. **Split discipline**: every method, threshold, prior, and default developed
   on the exploratory set only; confirmatory + holdout run exactly once at the
   end with frozen methods.
2. **Holdout**: included in the final one-shot run (matches the 32,487 total;
   the holdout was publicly released in 2021).
3. **Baseline convention**: earliest-created package = incumbent baseline
   (arm 0); stated in UI/docs; re-pickable in the dashboard.
4. **Sequential replay**: no event-level data exists, so within-test
   trajectories are conditional permutation replays (exact given final counts)
   and are labeled as reconstructions. Corpus-level peeking damage is measured
   on simulated streams with known truth.
5. **Validation rule**: any statistical routine that cannot be validated
   against simulation or a reference implementation is flagged, not shipped.

## Milestones (as executed)

1. abkit core + simulation tests (freq/design/bayes/health/multiplicity/shrinkage)
2. sequential module (mSPRT, confidence sequences, MC-calibrated O'Brien-Fleming)
3. ingest: checksummed downloads, count validation, bundled 50-test CI sample
4. exploratory meta-analysis (priors → batch readouts → figures)
5. dashboard: readout page
6. dashboard: sequential replay, design-a-test, corpus explorer
7. confirmatory + holdout, run once
8. writeup (README, RESULTS.md, notebook)

## Risks called out in advance

- OSF availability → checksummed cache; CI never downloads (bundled sample).
- Zero-click arms / tiny tests → Wilson/Newcombe everywhere, explicit gates,
  relative lift reported as undefined rather than invented.
- mSPRT mixture variance (phi) tuning affects power, never validity → set from
  the corpus prior (phi ≈ E[theta²]), sensitivity documented.
- Empirical-Bayes prior misfit → time-split calibration check (fit early weeks,
  score late weeks; z-dispersion 1.06 ≈ 1).
- SRM interpretation: flags mean "allocation not uniform", not necessarily
  "randomization broken" — investigated, mechanism not recoverable from
  aggregates; flagged tests excluded from all win counts.
