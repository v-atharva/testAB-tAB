"""Shared UI helpers: verdict banners, health badges, chart chrome."""

from __future__ import annotations

import plotly.graph_objects as go

from abkit.readout import Readout, Verdict
from dashboard import theme

BLUE = "#2a78d6"
ORANGE = "#eb6834"
MUTED = "#898781"


def pct(x: float, digits: int = 1, signed: bool = True) -> str:
    sign = "+" if signed else ""
    return f"{x * 100:{sign}.{digits}f}%"


def style_fig(fig: go.Figure) -> go.Figure:
    """Chart chrome consistent with the design system (data colors unchanged)."""
    fig.update_layout(
        font={"family": "IBM Plex Sans, sans-serif", "color": "#465062", "size": 12.5},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel={
            "bgcolor": "#101623",
            "bordercolor": "#101623",
            "font": {"family": "IBM Plex Mono, monospace", "color": "#f6f8fb", "size": 12},
        },
        transition={"duration": 250, "easing": "cubic-in-out"},
    )
    fig.update_xaxes(gridcolor="#e4e8f0", zerolinecolor="#c9cfdb")
    fig.update_yaxes(gridcolor="#e4e8f0", zerolinecolor="#c9cfdb")
    return fig


def verdict_banner(r: Readout) -> None:
    """The headline decision, colored by decision quality — never by lift size."""
    kind = {
        Verdict.SHIP_VARIANT: "ship",
        Verdict.KEEP_BASELINE: "keep",
        Verdict.UNDERPOWERED: "warn",
        Verdict.INSUFFICIENT_DATA: "warn",
        Verdict.INVALID_SRM: "invalid",
    }[r.verdict]
    theme.verdict_card(kind, r.headline, list(r.notes))


def health_badges(r: Readout) -> None:
    power_dot = "ok" if r.achieved_power >= 0.5 else "warn"
    theme.stat_grid(
        [
            {
                "label": "SRM · traffic split",
                "value": "pass" if not r.srm.failed else "FAIL",
                "dot": "ok" if not r.srm.failed else "fail",
                "tone": "" if not r.srm.failed else "bad",
                "sub": f"chi-square p = {r.srm.p_value:.3g} vs an even split",
            },
            {
                "label": "minimum sample",
                "value": "pass" if not r.quality.gated else "FAIL",
                "dot": "ok" if not r.quality.gated else "fail",
                "tone": "" if not r.quality.gated else "bad",
                "sub": "per-arm and total impression gates from config",
            },
            {
                "label": "zero-click arms",
                "value": str(len(r.quality.zero_click_arms)),
                "dot": "ok" if not r.quality.zero_click_arms else "warn",
                "sub": "relative lift undefined for these arms — shown as such",
            },
            {
                "label": "achieved power",
                "value": f"{r.achieved_power:.0%}",
                "dot": power_dot,
                "sub": f"vs a corpus-typical lift ({pct(r.benchmark_rel_lift)} relative)",
            },
        ]
    )
