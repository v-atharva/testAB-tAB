# 🧪 Upworthy Readout: An Experiment Readout Engine and Decision Dashboard for 32,487 Real A/B Tests

Every headline/image A/B test Upworthy.com ran between January 2013 and April 2015 - 32,487 experiments, 150,817 arms, ~538 million participant assignments ([Upworthy Research Archive](https://upworthy.natematias.com/about-the-archive.html), [Nature Scientific Data](https://www.nature.com/articles/s41597-021-00934-7)) - re-analyzed with the statistics an experimentation platform should have applied.
We built a reusable statistics library, a batch analysis pipeline, and a dashboard that renders a decision-grade readout for any of those experiments.

A readout must get five things right: health checks before inference (a broken traffic split invalidates a test, it doesn't decide it); corrections for testing many arms and many experiments; the winner's curse (the arm you noticed *because it won* is exaggerated by selection); power against effects that actually occur, so "not significant" is never silently read as "no effect"; and anytime-valid methods if anyone will peek before the end.
This repo demonstrates all five, on real data, at scale.

<p align="center"><img src="outputs/figures/dashboard/readout_page.png" width="85%"></p>

---

### Headline Findings

We analyzed 27,612 tests (22,741 confirmatory + 4,871 holdout; 2 single-arm tests dropped) exactly once, with methods frozen from the exploratory set:

1. **Winner's curse is huge.**
   The median winning arm claims **+96%** relative CTR lift; the shrinkage-corrected estimate is **+50%** - a median exaggeration of **×1.69**.
   Selection bias grows as power falls (see figure).
2. **Most "wins" evaporate under honest accounting.**
   5,009 tests have an uncorrected significant winner; 3,197 survive within-test Holm; 1,554 survive corpus-level BH.
   That is **69% of naive wins gone**.
3. **The corpus was underpowered for its own effect sizes.**
   Median power to detect a corpus-typical lift (+35% relative) was **32%**, and only **3.5%** of tests reached the 80% planning bar.
   Verdicts: 55.8% "underpowered - don't conclude", 17.1% keep baseline, 11.6% ship a variant.
4. **Peeking would have wrecked it.**
   Stop-at-first-p<0.05 hits a 22-27% false-positive rate at 20-50 looks on null streams, while mSPRT stays ≤0.5% monitored continuously.
   Replaying real no-winner tests, naive peeking shows a phantom mid-test "win" in **38%** of them.
5. **15.4% of tests fail SRM** (traffic split inconsistent with uniform randomization at p<0.001, ~150× the nominal rate).
   All 4,259 of them are excluded from every count above.
6. **Upworthy's own declared winners rarely survive.**
   Of 6,502 tests where their tooling declared a winner, only **19.9%** are confirmed by the corrected analysis; 51% were declared from underpowered tests.

Every one of these replicated out-of-sample: exploratory, confirmatory, and holdout give exaggeration ×1.65 / ×1.69 / ×1.73, evaporation 70% / 69% / 68%, median power 32% in all three, and SRM 15.5% / 15.5% / 15.0%.
Per-set numbers live in `outputs/results/{set}_summary.json`.

<p align="center"><img src="outputs/figures/confirmatory/winners_curse.png" width="90%"></p>

The exploratory/confirmatory discipline is itself part of the demonstration: the archive ships pre-split, and **every method, threshold, prior, and default here was developed on the exploratory set only** (4,873 tests).
The confirmatory + holdout sets (27,614 tests) were analyzed exactly once, with methods frozen, to produce the numbers above.
No result from those sets fed back into any choice.

---

### Technology Stack

We have used a combination of the following technologies:

1. **Python 3.11+** - the core language for the statistics library, the pipeline, and the dashboard.
2. **NumPy + SciPy** - vectorized Monte Carlo, distributions, optimization, and quadrature behind every statistical routine.
3. **Pandas + PyArrow** - data manipulation in the analysis layer and compact Parquet results the dashboard reads.
4. **Streamlit** - the four-page, read-only decision dashboard.
5. **Plotly** - interactive charts inside the dashboard.
6. **Matplotlib** - the static meta-analysis figures in `outputs/figures/`.
7. **uv** - fast, lockfile-driven environment management, used identically in development, CI, and Docker.
8. **pytest + statsmodels** - the simulation-validation test suite; statsmodels appears only as a reference implementation to validate against.

We have kept **abkit**, the statistics core, free of pandas and I/O because pure functions on counts are trivially testable by simulation and reusable outside this project.

---

### The Three Components

1. **`abkit` - a reusable experimentation library (`src/abkit/`).**
   Pure typed functions on counts: design (power / MDE / sample size), frequentist readout (two-proportion z, Wilson & Newcombe & Katz intervals, k-arm chi-square), sequential inference (mSPRT always-valid p-values and confidence sequences, Monte-Carlo-calibrated O'Brien-Fleming boundaries for contrast), multiplicity (Holm within a test, Benjamini-Hochberg across a corpus), empirical-Bayes shrinkage with winner's-curse estimators, Beta-Binomial Bayesian readout (P(best), expected loss), and health checks (SRM, minimum-sample gates) - composed into one verdict by `abkit.readout`.
   **Every statistical routine is validated in `tests/` against simulation or a reference implementation**: empirical type-I error ≈ α, CI coverage ≈ nominal, shrinkage posterior calibration, mSPRT error control under *continuous* monitoring (while the naive repeated z-test demonstrably inflates), and O'Brien-Fleming constants recovered against published values.
2. **Corpus meta-analysis (`src/analysis/`).**
   Checksummed OSF ingest, count validation against the published totals, corpus priors fit on the exploratory set (frozen thereafter), batch readouts, then the figures in `outputs/figures/` and the numbers above.
3. **Decision dashboard (`src/dashboard/`, Streamlit).**
   A readout tool, not a chart gallery.
   Four screens: **experiment readout** (verdict, naive *vs* corrected lift with intervals, Bayesian panel, health badges, achieved power - every number with a plain-English line a non-statistician can act on), **sequential monitoring** (replay a test with a narrowing confidence sequence, a "could have safely stopped here" marker, and the naive peeking rejections it avoids), **design-a-test** (power/MDE anchored to the corpus prior: *plan for lifts that actually occur*), and the **corpus explorer**.
   Read-only over precomputed parquet; an uncorrected significant result is never presented as a win anywhere in the UI.

---

### Set Up

#### 1 Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/<yourusername>/upworthy-readout.git
   cd upworthy-readout
   ```

2. Install the environment (uv, Python 3.11+):
   `make setup`

#### 2 Data Setup

Precomputed batch results are committed, so the dashboard works immediately after cloning - no downloads needed:
   `make dashboard`

For a full reproduction, download the archive from OSF (checksummed, cached, ~95 MB):
   `make data`

#### 3 Running the Pipeline

1. Fit the corpus priors (exploratory set only, frozen thereafter):
   `make priors`

2. Batch readouts + meta-analysis figures on the exploratory set:
   `make analysis`

3. Run the test suite (82 tests, including the simulation-validation suite):
   `make test`

4. The one-shot final run on confirmatory + holdout (intentionally run once):
   `make confirmatory`

5. Launch the Streamlit dashboard:
   `make dashboard`

Docker alternative: `docker build -t upworthy-readout . && docker run -p 8501:8501 upworthy-readout`.
CI runs lint (ruff), types (mypy strict), the full test suite, and an end-to-end pipeline smoke run on a committed 50-test sample - it never downloads the archive.

---

### Methods Appendix

- **Baseline convention.**
  The archive designates no control arm; the earliest-created package is treated as the incumbent baseline (stated in the UI, re-pickable in the dashboard).
  Only 2.6% of tests are 2-arm; the modal test has 4 arms, so k-arm corrections are the norm, not an edge case.
- **Intervals.**
  Wilson per arm; Newcombe hybrid for absolute lift; Katz log-scale for relative lift.
  At 1.5% CTR, Wald intervals are unreliable and are not used.
  Zero-click arms are legal inputs: the relative lift is reported as *undefined* there, never as a number.
- **Shrinkage.**
  theta = log-odds lift vs baseline; theta_hat ~ N(theta, se²) with Woolf variance; theta ~ N(mu, tau²) fit by marginal MLE on exploratory (mu = -0.064: later-created variants run slightly worse than the incumbent on average; tau = 0.303: a one-sd true lift is ~35% relative - headline effects at Upworthy were large and heterogeneous).
  Time-split calibration (fit early weeks, score late weeks) gives z-dispersion 1.06 ≈ 1.
  Posterior means are the "corrected" lifts everywhere.
  Odds-ratio ≈ risk-ratio at these CTRs (documented approximation).
- **Sequential.**
  mSPRT with a normal mixture on the absolute lift; mixture variance phi = 2.5e-5 ≈ E[theta²] under the corpus prior (validity holds for any phi; only power depends on it).
  Confidence sequences come from the same martingale.
  No event-level data exists, so dashboard replays are **conditional permutation replays** - exact given the final counts, labeled as reconstructions.
  Corpus peeking-damage numbers come from simulated streams with known truth.
- **Multiplicity.**
  Holm across a test's pairwise-vs-baseline comparisons (family-wise control for "ship X"); BH at q=0.05 across the corpus on the per-test Holm-corrected p (FDR control for "how many wins are there").
- **SRM.**
  Chi-square against uniform allocation at α=1e-3.
  A large share of archive tests fail (15.5% exploratory).
  We checked the obvious mechanism - arms added mid-test - and it does *not* explain the failures (failing tests have *smaller* arm-creation spreads).
  The cause is not recoverable from aggregate data; flagged tests are excluded from all win counts, which is the correct platform behavior regardless of mechanism.
- **Power.**
  "Achieved power" is against a one-prior-sd true lift - the size of effect this corpus actually produces - not an arbitrary MDE.
- **Every default** (α=0.05, SRM α=1e-3, gates, phi, MC draws, seeds) lives in `config/defaults.yaml`; the fitted priors live in `config/fitted_priors.yaml` with provenance.

---

### Limitations

- **One metric.**
  Clicks/impressions only.
  No downstream engagement, no guardrails; a real decision would weigh more than CTR.
- **2013-15 media context.**
  Upworthy-era curiosity-gap headlines; effect sizes and feature findings should not be extrapolated to other products or eras.
- **No user-level data.**
  Aggregates per arm only: no CUPED (nothing to covary on), no interference or novelty-effect checks, and sequential replays are reconstructions, not logs.
- **SRM mechanism unknown.**
  We can flag and exclude, but not diagnose, the allocation anomalies.
- **External validity.**
  One company, one surface, one outcome.
  The *methods* transfer; the *numbers* describe this corpus.

---

### Future Work

Extensions this archive cannot support (mostly for lack of user-level data), but that follow naturally from the methods here:

- **Guardrail metrics with non-inferiority gates** - a CTR win that hurts retention or revenue is a loss; verdicts should require "primary wins AND guardrails don't regress (one-sided non-inferiority)".
- **CUPED / regression adjustment** on user-level pre-exposure covariates - the standard 30-50% variance reduction (Deng et al., 2013) this archive can't demonstrate for lack of user data.
- **Automated SRM triage**, not just detection: segment-level chi-squares (browser, geo, day) to localize the broken slice, and quarantine rules.
- **Interference & novelty checks** - switchback or cluster designs where units interact; first-week vs later-week effect comparison before shipping.
- **Corpus-level holdouts** - a standing 5% global holdout to measure the *cumulative* effect of shipped wins against the shrinkage predictions (the winner's-curse ledger, closed).
- **Decision memos as artifacts** - the dashboard's verdict block, persisted and versioned per experiment, so "why did we ship this" has an answer a year later.

---

### Repo Map

```
src/abkit/        the library (typed, tested, importable on its own)
src/analysis/     ingest -> priors -> batch readouts -> meta-analysis figures
src/dashboard/    Streamlit app (4 pages, read-only)
config/           every default + frozen fitted priors
data/sample/      committed 50-test sample (CI smoke runs; raw schema)
notebooks/        one narrative notebook (executes cleanly end-to-end)
outputs/          figures + committed batch results
tests/            82 tests; the simulation-validation suite is the point
```

---

### References

Every method in this project traces to published work; the citations below are grouped by the role they play.
Where a routine implements a specific paper, the module is noted in parentheses.

#### Dataset

1. Matias, J.N., Munger, K., Le Quere, M.A., & Ebersole, C. (2021). The Upworthy Research Archive, a time series of 32,487 experiments in U.S. media. *Scientific Data*, 8, 195. [doi:10.1038/s41597-021-00934-7](https://doi.org/10.1038/s41597-021-00934-7).
   Distributed for research via [OSF (node jd64p)](https://osf.io/jd64p/), courtesy of Good Inc. and the archive team.

#### Statistical methodology

2. Wilson, E.B. (1927). Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association*, 22(158), 209-212. [doi:10.1080/01621459.1927.10502953](https://doi.org/10.1080/01621459.1927.10502953). (Per-arm CTR intervals, `abkit.freq`.)
3. Newcombe, R.G. (1998). Interval estimation for the difference between independent proportions: comparison of eleven methods. *Statistics in Medicine*, 17(8), 873-890. [doi:10.1002/(SICI)1097-0258(19980430)17:8<873::AID-SIM779>3.0.CO;2-I](https://doi.org/10.1002/(SICI)1097-0258(19980430)17:8%3C873::AID-SIM779%3E3.0.CO;2-I). (Absolute-lift intervals, method 10.)
4. Katz, D., Baptista, J., Azen, S.P., & Pike, M.C. (1978). Obtaining confidence intervals for the risk ratio in cohort studies. *Biometrics*, 34(3), 469-474. [doi:10.2307/2530610](https://doi.org/10.2307/2530610). (Relative-lift intervals.)
5. Woolf, B. (1955). On estimating the relation between blood group and disease. *Annals of Human Genetics*, 19(4), 251-253. [doi:10.1111/j.1469-1809.1955.tb01348.x](https://doi.org/10.1111/j.1469-1809.1955.tb01348.x). (Log-odds lift variance, `abkit.shrinkage`.)
6. Fleiss, J.L., Levin, B., & Paik, M.C. (2003). *Statistical Methods for Rates and Proportions* (3rd ed.). Wiley. [doi:10.1002/0471445428](https://doi.org/10.1002/0471445428). (Power/sample-size formulas, `abkit.design`.)
7. Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65-70. [jstor.org/stable/4615733](https://www.jstor.org/stable/4615733). (Within-test familywise correction.)
8. Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*, 57(1), 289-300. [doi:10.1111/j.2517-6161.1995.tb02031.x](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x). (Corpus-level FDR control.)
9. Johari, R., Koomen, P., Pekelis, L., & Walsh, D. (2017). Peeking at A/B tests: why it matters, and what to do about it. *Proceedings of KDD '17*. [doi:10.1145/3097983.3097992](https://doi.org/10.1145/3097983.3097992). (mSPRT always-valid p-values, `abkit.sequential`.)
10. Johari, R., Pekelis, L., & Walsh, D.J. (2022). Always valid inference: continuous monitoring of A/B tests. *Operations Research*, 70(3), 1806-1821. [doi:10.1287/opre.2021.2135](https://doi.org/10.1287/opre.2021.2135). (Confidence sequences from the mixture martingale.)
11. Howard, S.R., Ramdas, A., McAuliffe, J., & Sekhon, J. (2021). Time-uniform, nonparametric, nonasymptotic confidence sequences. *Annals of Statistics*, 49(2), 1055-1080. [doi:10.1214/20-AOS1991](https://doi.org/10.1214/20-AOS1991). (The modern confidence-sequence framework; Ville's inequality underlies the anytime guarantee.)
12. O'Brien, P.C., & Fleming, T.R. (1979). A multiple testing procedure for clinical trials. *Biometrics*, 35(3), 549-556. [doi:10.2307/2530245](https://doi.org/10.2307/2530245). (Group-sequential boundaries used as the classical contrast.)
13. Efron, B., & Morris, C. (1975). Data analysis using Stein's estimator and its generalizations. *Journal of the American Statistical Association*, 70(350), 311-319. [doi:10.1080/01621459.1975.10479864](https://doi.org/10.1080/01621459.1975.10479864). (Normal-normal empirical-Bayes shrinkage.)
14. Gelman, A., & Carlin, J. (2014). Beyond power calculations: assessing Type S (sign) and Type M (magnitude) errors. *Perspectives on Psychological Science*, 9(6), 641-651. [doi:10.1177/1745691614551642](https://doi.org/10.1177/1745691614551642). (The exaggeration-factor framing behind `expected_winner_exaggeration`.)
15. van Zwet, E.W., & Cator, E.A. (2021). The significance filter, the winner's curse and the need to shrink. *Statistica Neerlandica*, 75(4), 437-452. [doi:10.1111/stan.12241](https://doi.org/10.1111/stan.12241). (Why selected estimates must be shrunk.)

#### Industry practice

16. Kohavi, R., Tang, D., & Xu, Y. (2020). *Trustworthy Online Controlled Experiments: A Practical Guide to A/B Testing*. Cambridge University Press. [doi:10.1017/9781108653985](https://doi.org/10.1017/9781108653985). (The reference for platform practice: SRM as an invalidation gate, guardrails, correction conventions.)
17. Kohavi, R., Longbotham, R., Sommerfield, D., & Henne, R.M. (2009). Controlled experiments on the web: survey and practical guide. *Data Mining and Knowledge Discovery*, 18, 140-181. [doi:10.1007/s10618-008-0114-1](https://doi.org/10.1007/s10618-008-0114-1).
18. Crook, T., Frasca, B., Kohavi, R., & Longbotham, R. (2009). Seven pitfalls to avoid when running controlled experiments on the web. *Proceedings of KDD '09*. [doi:10.1145/1557019.1557139](https://doi.org/10.1145/1557019.1557139). (Peeking and novelty-effect pitfalls.)
19. Fabijan, A., Gupchup, J., Gupta, S., Omhover, J., Qin, W., Vermeer, L., & Dmitriev, P. (2019). Diagnosing sample ratio mismatch in online controlled experiments. *Proceedings of KDD '19*. [doi:10.1145/3292500.3330722](https://doi.org/10.1145/3292500.3330722). (SRM taxonomy and the strict-alpha convention.)
20. Deng, A., Xu, Y., Kohavi, R., & Walker, T. (2013). Improving the sensitivity of online controlled experiments by utilizing pre-experiment data (CUPED). *Proceedings of WSDM '13*. [doi:10.1145/2433396.2433413](https://doi.org/10.1145/2433396.2433413). (The variance-reduction technique noted under Future Work.)
21. Lee, M.R., & Shen, M. (2018). Winner's curse: bias estimation for total effects of features in online controlled experiments. *Proceedings of KDD '18*. [doi:10.1145/3219819.3219905](https://doi.org/10.1145/3219819.3219905). (The winner's curse measured inside an industry platform.)
22. Stucchio, C. (2015). *Bayesian A/B Testing at VWO* (technical whitepaper). [vwo.com/downloads/VWO_SmartStats_technical_whitepaper.pdf](https://vwo.com/downloads/VWO_SmartStats_technical_whitepaper.pdf). (The expected-loss decision rule used in the Bayesian panel.)
