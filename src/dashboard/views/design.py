"""Design-a-test: power / MDE / sample size, anchored to the corpus prior."""

from __future__ import annotations

import math

import streamlit as st

from abkit import design
from dashboard import data, ui


def render() -> None:
    st.title("Design a test")
    cfg = data.config()
    prior = cfg.readout.lift_prior
    ctr_mean = cfg.readout.ctr_prior.mean
    typical_rel = math.exp(prior.tau) - 1

    st.caption(
        f"Anchored to reality: across this corpus, a typical true lift is "
        f"about **{ui.pct(typical_rel)} relative** (one sd of the fitted prior "
        f"on true lifts), around a mean CTR of **{ctr_mean:.1%}**. Plan for "
        "effects that actually occur, not for the ones you hope for."
    )

    c1, c2, c3 = st.columns(3)
    p0 = c1.number_input("Baseline CTR (%)", 0.1, 50.0, round(ctr_mean * 100, 2), 0.1) / 100
    alpha = c2.selectbox("alpha (two-sided)", [0.05, 0.01, 0.10], index=0)
    power = c3.selectbox("target power", [0.80, 0.90, 0.95], index=0)

    st.subheader("How many impressions per arm do I need?")
    rel = st.slider(
        "relative lift to detect (%)", 1.0, 100.0, round(typical_rel * 100, 1), 0.5,
        help="The corpus-typical lift is preselected.",
    ) / 100
    p1 = min(0.999, p0 * (1 + rel))
    n_needed = design.sample_size_two_prop(p0, p1, alpha=alpha, power=power)
    st.metric(
        f"impressions per arm for {power:.0%} power vs a {rel:.0%} lift",
        f"{n_needed:,}",
    )
    median_arm = 3122  # exploratory median, documented in the README
    ratio = n_needed / median_arm
    if ratio > 1:
        st.caption(
            f"The median archived Upworthy arm had ~{median_arm:,} impressions — "
            f"this plan needs **{ratio:.1f}x that**. The gap is why most of the "
            "archive is underpowered."
        )

    st.subheader("What could a test of my size actually detect?")
    n_have = st.number_input("impressions per arm", 100, 10_000_000, median_arm, 100)
    mde_abs = design.mde_two_prop(p0, int(n_have), alpha=alpha, power=power)
    mde_rel = mde_abs / p0
    achieved = design.power_two_prop(p0, p0 * (1 + typical_rel), int(n_have), alpha)
    m1, m2 = st.columns(2)
    m1.metric("minimum detectable lift (relative)", ui.pct(mde_rel, signed=False), help=(
        f"The smallest upward lift detectable with {power:.0%} power: "
        f"{mde_abs * 100:.2f} pp absolute on a {p0:.1%} baseline."
    ))
    m2.metric("power vs a corpus-typical lift", f"{achieved:.0%}", help=(
        f"Probability this test would detect a {ui.pct(typical_rel)} relative "
        "lift if one were truly there."
    ))
    if achieved < 0.5:
        st.warning(
            "Below 50% power for realistic effects: a null result from this "
            "design says almost nothing. Increase traffic or accept a longer test."
        )
