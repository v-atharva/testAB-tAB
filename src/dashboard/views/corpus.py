"""Corpus explorer: the meta-analysis findings, interactive."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from analysis.paths import RESULTS_DIR
from dashboard import data, ui


def _summary(dataset: str) -> dict[str, Any]:
    path = RESULTS_DIR / f"{dataset}_summary.json"
    if not path.exists():
        return {}
    with path.open() as f:
        loaded: dict[str, Any] = json.load(f)
    return loaded


def render() -> None:
    st.title("Corpus explorer")
    datasets = data.available_datasets()
    if not datasets:
        st.error("No batch results found. Run `make analysis` first.")
        return
    dataset = st.selectbox("Dataset", datasets)
    tests = data.tests_table(dataset)
    summary = _summary(dataset)

    # ---------------- headline numbers -------------------------------------
    wc = summary.get("winners_curse", {})
    fdr = summary.get("fdr", {})
    pw = summary.get("power", {})
    srm = summary.get("srm", {})
    c1, c2, c3, c4 = st.columns(4)
    if wc:
        c1.metric("median winner exaggeration", f"x{wc['median_exaggeration_ratio']:.2f}",
                  help="Naive winning-arm lift / shrinkage-corrected lift, among "
                       "corrected winners.")
    if fdr:
        c2.metric("naive wins that evaporate", f"{fdr['frac_naive_wins_evaporating']:.0%}",
                  help="Uncorrected p<.05 wins that do not survive within-test Holm "
                       "+ corpus-level BH correction.")
    if pw:
        c3.metric("tests with ≥80% power", f"{pw['frac_tests_power_ge_80']:.1%}",
                  help="Against a corpus-typical true lift (one prior sd).")
    if srm:
        c4.metric("SRM failures", f"{srm['rate']:.1%}",
                  help="Tests whose traffic split deviates from uniform at p<0.001. "
                       "Excluded from all win counts.")

    st.divider()

    # ---------------- winner's curse, interactive ---------------------------
    st.subheader("Winner's curse: naive vs corrected winner lift")
    st.caption(
        "Each point is an experiment with a corrected significant winner. "
        "Distance below the diagonal is selection-bias exaggeration. Hover for "
        "the experiment; low-power tests fall furthest."
    )
    win = tests[tests["sig_corrected"] & tests["winner_rel_lift_naive"].notna()]
    if not win.empty:
        arms = data.arms_table(dataset)
        base_hl = arms[arms["arm_idx"] == 0].set_index("test_id")["headline"]
        hover = win["test_id"].map(base_hl).fillna("").str.slice(0, 70)
        lim = float(np.percentile(win["winner_rel_lift_naive"], 98)) * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=win["winner_rel_lift_naive"] * 100, y=win["winner_rel_lift_shrunk"] * 100,
            mode="markers",
            marker={"color": ui.BLUE, "size": 6, "opacity": 0.45},
            text=hover, name="experiments",
            hovertemplate="naive %{x:.0f}% → corrected %{y:.0f}%<br>%{text}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[0, lim], y=[0, lim], mode="lines",
            line={"color": ui.MUTED, "dash": "dash", "width": 1.5},
            name="y = x (no exaggeration)",
        ))
        fig.update_xaxes(title="naive winner lift (relative, %)", range=[0, lim])
        fig.update_yaxes(title="shrinkage-corrected lift (%)", range=[0, lim])
        fig.update_layout(height=480, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                          legend={"orientation": "h", "y": 1.08})
        st.plotly_chart(fig, use_container_width=True)

    # ---------------- power distribution ------------------------------------
    st.subheader("Achieved power across the corpus")
    ok = tests[~tests["srm_failed"]]
    fig2 = go.Figure(go.Histogram(
        x=ok["achieved_power"], nbinsx=40, marker={"color": ui.BLUE},
        hovertemplate="power %{x:.2f}: %{y} tests<extra></extra>",
    ))
    fig2.add_vline(x=0.8, line_dash="dash", line_color=ui.MUTED,
                   annotation_text="80% planning bar")
    fig2.update_xaxes(title="power to detect a corpus-typical lift")
    fig2.update_yaxes(title="experiments")
    fig2.update_layout(height=380, margin={"l": 10, "r": 10, "t": 10, "b": 10})
    st.plotly_chart(fig2, use_container_width=True)

    # ---------------- FDR bars ----------------------------------------------
    if fdr:
        st.subheader("How many 'wins' survive honest accounting?")
        labels = ["uncorrected (p < .05)", "within-test Holm", "+ BH across corpus"]
        counts = [fdr["wins_uncorrected"], fdr["wins_holm"], fdr["wins_holm_plus_bh"]]
        fig3 = go.Figure(go.Bar(
            y=labels[::-1], x=counts[::-1], orientation="h",
            marker={"color": ["#256abf", "#5598e7", "#9ec5f4"]},
            text=[f"{c:,}" for c in counts[::-1]], textposition="outside",
            hovertemplate="%{y}: %{x:,} wins<extra></extra>",
        ))
        fig3.update_xaxes(title="experiments with a declared winner")
        fig3.update_layout(height=300, margin={"l": 10, "r": 10, "t": 10, "b": 10})
        st.plotly_chart(fig3, use_container_width=True)

    # ---------------- verdicts + Upworthy audit -----------------------------
    st.subheader("Verdict distribution and the Upworthy audit")
    v1, v2 = st.columns(2)
    vc = tests["verdict"].value_counts()
    fig4 = go.Figure(go.Bar(
        y=vc.index.tolist()[::-1], x=vc.to_numpy()[::-1], orientation="h",
        marker={"color": ui.BLUE},
        text=[f"{c:,}" for c in vc.to_numpy()[::-1]], textposition="outside",
    ))
    fig4.update_layout(height=300, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                       xaxis_title="experiments")
    v1.plotly_chart(fig4, use_container_width=True)
    ua = summary.get("upworthy_audit", {})
    if ua and ua.get("n_declared"):
        v2.markdown(
            f"Upworthy's own tooling declared a winner in **{ua['n_declared']:,} tests** "
            f"({ua['frac_of_tests']:.0%} of the corpus). Re-analyzed with health checks, "
            f"corrections, and shrinkage:\n\n"
            f"- **{ua['frac_confirmed_by_corrected_analysis']:.0%} confirmed** "
            "(their pick survives corrected analysis)\n"
            f"- {ua['frac_underpowered_verdict']:.0%} came from underpowered tests\n"
            f"- {ua['frac_srm_failed']:.0%} came from tests failing SRM\n"
            f"- {ua['frac_winner_is_baseline_arm']:.0%} of declared winners were the "
            "earliest-created arm itself"
        )
