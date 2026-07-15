"""The core screen: a decision-grade readout for any experiment."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from abkit.readout import Readout
from dashboard import data, theme, ui


def _arm_label(arms_df: pd.DataFrame, i: int) -> str:
    headline = arms_df.loc[arms_df["arm_idx"] == i, "headline"].iloc[0]
    return f"arm {i} — {str(headline)[:60]}"


def _lift_figure(r: Readout, arm_labels: dict[int, str]) -> go.Figure:
    """Naive vs shrunk relative lift, side by side per variant."""
    fig = go.Figure()
    for i, c in enumerate(r.comparisons):
        name = arm_labels[c.arm_index]
        if c.rel_lift is not None and c.rel_lift_ci is not None:
            fig.add_trace(go.Scatter(
                x=[c.rel_lift * 100], y=[i + 0.15],
                error_x={"type": "data",
                         "array": [(c.rel_lift_ci.hi - c.rel_lift) * 100],
                         "arrayminus": [(c.rel_lift - c.rel_lift_ci.lo) * 100],
                         "color": ui.ORANGE, "thickness": 2},
                mode="markers", marker={"color": ui.ORANGE, "size": 9},
                name="naive", legendgroup="naive", showlegend=(i == 0),
                hovertemplate=f"{name} naive: %{{x:.1f}}%<extra></extra>",
            ))
        if c.shrunk_rel_lift is not None and c.shrunk_rel_ci is not None:
            fig.add_trace(go.Scatter(
                x=[c.shrunk_rel_lift * 100], y=[i - 0.15],
                error_x={"type": "data",
                         "array": [(c.shrunk_rel_ci[1] - c.shrunk_rel_lift) * 100],
                         "arrayminus": [(c.shrunk_rel_lift - c.shrunk_rel_ci[0]) * 100],
                         "color": ui.BLUE, "thickness": 2},
                mode="markers", marker={"color": ui.BLUE, "size": 9},
                name="shrinkage-corrected", legendgroup="shrunk", showlegend=(i == 0),
                hovertemplate=f"{name} corrected: %{{x:.1f}}%<extra></extra>",
            ))
    fig.add_vline(x=0, line_dash="dash", line_color=ui.MUTED, line_width=1)
    fig.update_yaxes(
        tickvals=list(range(len(r.comparisons))),
        ticktext=[arm_labels[c.arm_index] for c in r.comparisons],
        autorange="reversed",
    )
    fig.update_xaxes(title="relative lift vs baseline (%), 95% intervals")
    fig.update_layout(
        height=120 + 90 * len(r.comparisons), margin={"l": 10, "r": 10, "t": 10, "b": 10},
        legend={"orientation": "h", "y": 1.12},
    )
    return fig


def render() -> None:
    theme.hero(
        "Experiment readout",
        "Pick any archived experiment. The verdict applies, in order: health "
        "checks → minimum sample → Holm-corrected comparison vs the baseline → "
        "power against corpus-realistic lifts. Baseline = earliest-created "
        "package (the archive designates no control; you can re-pick below).",
    )

    datasets = data.available_datasets()
    if not datasets:
        st.error("No batch results found. Run `make analysis` first.")
        return
    left, right = st.columns([1, 3])
    dataset = left.selectbox("Dataset", datasets, help=(
        "Methods were developed on the exploratory set only; confirmatory/"
        "holdout appear here after the one-shot final run."
    ))
    opts = data.test_options(dataset)
    row = right.selectbox(
        "Experiment (search by baseline headline)", opts.itertuples(),
        format_func=lambda r: str(r.label),
    )
    test_id = str(row.test_id)

    arms_df = data.experiment_arms(dataset, test_id)
    n_arms = len(arms_df)
    baseline_idx = 0
    if n_arms > 2:
        baseline_idx = int(st.selectbox(
            "Baseline arm (default: earliest-created)",
            arms_df["arm_idx"].tolist(), index=0,
            format_func=lambda i: _arm_label(arms_df, i),
        ))

    r = data.experiment_readout(dataset, test_id, baseline_idx)
    label_of = {i: f"arm {a}" for i, a in enumerate(
        [baseline_idx, *[i for i in arms_df["arm_idx"] if i != baseline_idx]]
    )}

    ui.verdict_banner(r)
    ui.health_badges(r)

    # ---------------- arms table -------------------------------------------
    theme.section("Arms")
    st.caption(
        "CTR with 95% Wilson intervals. P(best) and expected loss are Bayesian "
        "quantities under the corpus prior: use them to pick a forced winner, "
        "never as significance."
    )
    ordered = [baseline_idx, *[i for i in arms_df["arm_idx"] if i != baseline_idx]]
    display = arms_df.set_index("arm_idx").loc[ordered].reset_index()
    table = pd.DataFrame({
        "arm": [f"arm {int(i)}" + ("  (baseline)" if int(i) == baseline_idx else "")
                 for i in display["arm_idx"]],
        "headline": display["headline"].str.slice(0, 90),
        "impressions": display["impressions"],
        "clicks": display["clicks"],
        "CTR": [f"{a.ctr:.2%}" for a in r.arms],
        "95% CI": [f"[{a.ctr_ci.lo:.2%}, {a.ctr_ci.hi:.2%}]" for a in r.arms],
        "P(best)": [f"{a.p_best:.0%}" for a in r.arms],
        "expected loss (pp CTR)": [f"{a.expected_loss * 100:.3f}" for a in r.arms],
    })
    st.dataframe(table, hide_index=True, use_container_width=True)

    # ---------------- lifts -------------------------------------------------
    theme.section("Lift vs baseline — naive and shrinkage-corrected")
    st.caption(
        "Orange = the raw estimate (what a naive readout reports). Blue = the "
        "empirical-Bayes corrected estimate under the corpus prior — the number "
        "to plan around. Noisy tests get pulled hard toward the corpus mean; "
        "that pull IS the winner's-curse correction."
    )
    st.plotly_chart(ui.style_fig(_lift_figure(r, label_of)), use_container_width=True)

    # ---------------- statistics table -------------------------------------
    theme.section("Comparisons vs baseline (Holm-corrected family)")
    st.caption(
        f"Omnibus chi-square across all {len(r.arms)} arms: p = {r.omnibus_chi2_p:.3g}. "
        f"Pairwise p-values below are Holm-adjusted across the {len(r.comparisons)} "
        "comparisons — a variant only counts as a winner on the adjusted value."
    )
    comp_table = pd.DataFrame({
        "variant": [label_of[c.arm_index] for c in r.comparisons],
        "abs lift (pp)": [f"{c.abs_lift * 100:+.2f}" for c in r.comparisons],
        "abs 95% CI (pp)": [
            f"[{c.abs_lift_ci.lo * 100:+.2f}, {c.abs_lift_ci.hi * 100:+.2f}]"
            for c in r.comparisons
        ],
        "raw p": [f"{c.z_p_value:.3g}" for c in r.comparisons],
        "Holm-adjusted p": [f"{c.holm_p_value:.3g}" for c in r.comparisons],
        "significant (corrected)": ["yes" if c.significant else "no" for c in r.comparisons],
    })
    st.dataframe(comp_table, hide_index=True, use_container_width=True)

    with st.expander("How to read this (for non-statisticians)"):
        st.markdown(
            "- **Verdict** — the decision, with health checks applied before any "
            "statistics. An unhealthy or under-sampled test never yields a winner.\n"
            "- **Naive vs corrected lift** — the arm you noticed *because it looks "
            "best* is exaggerated by selection. The corrected value asks: given "
            "how noisy this test is and how big true lifts in this corpus "
            "actually are, what's the best guess for THIS arm's true lift?\n"
            "- **P(best)** — chance this arm is truly the best one. 90% is a fine "
            "forced pick and still not proof.\n"
            "- **Expected loss** — CTR you'd sacrifice on average by shipping this "
            "arm if it turns out not to be the best. Near zero = shipping is safe "
            "even without significance.\n"
            "- **Holm-adjusted p** — testing several variants against the baseline "
            "gives several chances to be fooled; the adjustment charges for them."
        )
