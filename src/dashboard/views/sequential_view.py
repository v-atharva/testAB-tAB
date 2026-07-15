"""Sequential monitoring view: replay a test with anytime-valid inference."""

from __future__ import annotations

import zlib

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from abkit import sequential
from dashboard import data, theme, ui

N_LOOKS = 60


def render() -> None:
    theme.hero(
        "Sequential monitoring — when could we have stopped?",
        "The archive records only final counts, so this is a <b>conditional-"
        "permutation replay</b>: the arm's actual clicks are streamed in random "
        "order, which is exact conditional on the observed totals. The shaded "
        "band is a 95% confidence sequence (mSPRT): valid at EVERY look "
        "simultaneously, so watching it daily is safe. The orange markers show "
        "where a naive repeated z-test would have called a winner — the "
        "malpractice this page is built to expose.",
    )

    datasets = data.available_datasets()
    if not datasets:
        st.error("No batch results found. Run `make analysis` first.")
        return
    left, right = st.columns([1, 3])
    dataset = left.selectbox("Dataset", datasets)
    opts = data.test_options(dataset)
    row = right.selectbox("Experiment", opts.itertuples(), format_func=lambda r: str(r.label))
    test_id = str(row.test_id)
    arms_df = data.experiment_arms(dataset, test_id)

    def _label(i: int) -> str:
        headline = arms_df.loc[arms_df["arm_idx"] == i, "headline"].iloc[0]
        return f"arm {i} — {str(headline)[:60]}"

    variants = [int(i) for i in arms_df["arm_idx"] if i != 0]
    variant = st.selectbox(
        "Variant (vs arm 0, the earliest-created baseline)", variants, format_func=_label
    )

    cfg = data.config()
    base = arms_df[arms_df["arm_idx"] == 0].iloc[0]
    var = arms_df[arms_df["arm_idx"] == variant].iloc[0]

    # deterministic replay per (test, arm): seed from config + test id
    seed = cfg.replay_seed ^ zlib.crc32(f"{test_id}/{variant}".encode())
    rng = np.random.default_rng(seed)
    k1 = sequential.conditional_permutation_replay(
        int(var["clicks"]), int(var["impressions"]), N_LOOKS, rng)
    k0 = sequential.conditional_permutation_replay(
        int(base["clicks"]), int(base["impressions"]), N_LOOKS, rng)
    n1 = sequential.replay_looks(int(var["impressions"]), N_LOOKS)
    n0 = sequential.replay_looks(int(base["impressions"]), N_LOOKS)

    trace = sequential.msprt_two_prop(k1, n1, k0, n0, phi=cfg.mixture_phi, alpha=cfg.alpha)
    naive_first = sequential.naive_peeking_rejections(k1, n1, k0, n0, cfg.alpha)

    frac = (n1 + n0) / (n1[-1] + n0[-1])
    theta_pp = trace.theta_hat * 100
    radius_pp = np.minimum(trace.cs_radius, 1.0) * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=np.concatenate([frac, frac[::-1]]) * 100,
        y=np.concatenate([theta_pp + radius_pp, (theta_pp - radius_pp)[::-1]]),
        fill="toself", fillcolor="rgba(42,120,214,0.15)",
        line={"width": 0}, hoverinfo="skip", showlegend=True,
        name="95% confidence sequence (anytime-valid)",
    ))
    fig.add_trace(go.Scatter(
        x=frac * 100, y=theta_pp, mode="lines",
        line={"color": ui.BLUE, "width": 2}, name="estimated lift (replay)",
        hovertemplate="%{x:.0f}% of traffic: %{y:+.3f} pp<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=ui.MUTED, line_width=1)

    # naive repeated-test rejections (all looks where naive p < alpha)
    from scipy import stats as sps
    pooled = (k1 + k0) / (n1 + n0)
    v = pooled * (1 - pooled) * (1 / n1 + 1 / n0)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(v > 0, (k1 / n1 - k0 / n0) / np.sqrt(v), 0.0)
    naive_sig = 2 * sps.norm.sf(np.abs(z)) < cfg.alpha
    if naive_sig.any():
        fig.add_trace(go.Scatter(
            x=frac[naive_sig] * 100, y=theta_pp[naive_sig], mode="markers",
            marker={"color": ui.ORANGE, "size": 7, "symbol": "x"},
            name="naive z-test says 'significant!' (p < .05, uncorrected for peeking)",
            hovertemplate="naive rejection at %{x:.0f}% of traffic<extra></extra>",
        ))

    if trace.first_rejection is not None:
        x_stop = float(frac[trace.first_rejection] * 100)
        fig.add_vline(x=x_stop, line_color=ui.BLUE, line_width=2, line_dash="dot")
        fig.add_annotation(x=x_stop, y=1.02, yref="paper",
                           text=f"safe stop: {x_stop:.0f}% of traffic",
                           showarrow=False, font={"color": ui.BLUE, "size": 12})

    fig.update_xaxes(title="% of total traffic observed")
    # clamp the y-range: the band is huge in the first few looks by design
    # (few observations), and letting it set the scale hides the useful region
    settled = radius_pp[len(radius_pp) // 6]
    y_lim = float(np.clip(3 * settled, 0.5, 25.0))
    fig.update_yaxes(title="lift, percentage points of CTR", range=[-y_lim, y_lim])
    fig.update_layout(height=480, margin={"l": 10, "r": 10, "t": 30, "b": 10},
                      legend={"orientation": "h", "y": -0.25})
    st.plotly_chart(ui.style_fig(fig), use_container_width=True)

    cards = []
    if trace.first_rejection is not None:
        cards.append({"label": "mSPRT verdict", "value": "significant", "dot": "ok",
                      "tone": "good",
                      "sub": f"could stop safely at {frac[trace.first_rejection]:.0%} of traffic"})
    else:
        cards.append({"label": "mSPRT verdict", "value": "no rejection", "dot": "warn",
                      "sub": "never crossed — cannot call a winner at any look"})
    cards.append({"label": "always-valid p · final", "value": f"{trace.always_valid_p[-1]:.3g}",
                  "sub": "valid despite continuous monitoring (mixture martingale)"})
    if naive_first is not None and trace.first_rejection is None:
        cards.append({"label": "naive peeking would have…", "value": "called a win",
                      "dot": "fail", "tone": "bad",
                      "sub": f"at {frac[naive_first]:.0%} of traffic — a phantom win"})
    elif naive_first is not None:
        cards.append({"label": "naive first 'significance'",
                      "value": f"{frac[naive_first]:.0%} traffic",
                      "sub": "uncorrected repeated testing; trust only if the "
                             "anytime-valid analysis agrees"})
    else:
        cards.append({"label": "naive peeking", "value": "never fired", "dot": "ok",
                      "sub": "no look reached p < 0.05 even uncorrected"})
    theme.stat_grid(cards)

    st.caption(
        "Replays are seeded and deterministic per experiment. Re-running the "
        "pipeline does not change them; they illustrate monitoring behavior, "
        "not new evidence beyond the final counts."
    )
