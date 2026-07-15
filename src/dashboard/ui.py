"""Shared UI helpers: verdict banners, health badges, formatting."""

from __future__ import annotations

import streamlit as st

from abkit.readout import Readout, Verdict

BLUE = "#2a78d6"
ORANGE = "#eb6834"
MUTED = "#898781"


def pct(x: float, digits: int = 1, signed: bool = True) -> str:
    sign = "+" if signed else ""
    return f"{x * 100:{sign}.{digits}f}%"


def verdict_banner(r: Readout) -> None:
    """The headline decision, colored by decision quality — never by lift size."""
    if r.verdict == Verdict.SHIP_VARIANT:
        st.success(f"**{r.headline}**", icon="✅")
    elif r.verdict == Verdict.KEEP_BASELINE:
        st.info(f"**{r.headline}**", icon="🧭")
    elif r.verdict in (Verdict.UNDERPOWERED, Verdict.INSUFFICIENT_DATA):
        st.warning(f"**{r.headline}**", icon="⚠️")
    else:  # INVALID_SRM
        st.error(f"**{r.headline}**", icon="🚨")
    for note in r.notes:
        st.caption(note)


def health_badges(r: Readout) -> None:
    cols = st.columns(4)
    srm = "✅ pass" if not r.srm.failed else "🚨 FAIL"
    cols[0].metric("SRM (traffic split)", srm, help=(
        "Chi-square test that impressions match the planned even split. "
        f"p = {r.srm.p_value:.3g}. A failure means assignment or logging broke; "
        "no lift from this test should be trusted."
    ))
    gates = "✅ pass" if not r.quality.gated else "🚨 FAIL"
    cols[1].metric("Minimum sample", gates, help=(
        "Gates from config: every arm above the per-arm impression minimum and "
        "the test above the total-impressions minimum."
    ))
    zc = len(r.quality.zero_click_arms)
    cols[2].metric("Zero-click arms", str(zc), help=(
        "Arms that never received a click. Their relative lift is undefined "
        "(reported as such, never as a number)."
    ))
    cols[3].metric("Achieved power", f"{r.achieved_power:.0%}", help=(
        "Power this test had to detect a corpus-typical true lift "
        f"({pct(r.benchmark_rel_lift)} relative — one prior sd). Below "
        "50% the verdict refuses to read 'no significance' as 'no effect'."
    ))
