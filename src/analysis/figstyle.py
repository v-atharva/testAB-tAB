"""Shared matplotlib style: validated palette + recessive chrome.

Palette pairs used here were run through the dataviz validator (CVD ΔE 24.7,
normal-vision ΔE 33.6, contrast >= 3:1 on the light surface — all pass).
Color assignment is by entity and fixed across every figure in the project:
naive/uncorrected is always ORANGE, corrected/valid methods are always BLUE,
references and nominal levels are muted gray dashes.
"""

from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# categorical (validated): corrected/valid = blue, naive/uncorrected = orange
BLUE = "#2a78d6"
ORANGE = "#eb6834"
BLUE_LIGHT = "#9ec5f4"  # sequential step 200, for fills under the blue line

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "font.family": "sans-serif",
            "font.size": 10,
            "text.color": INK,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK_SECONDARY,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "lines.linewidth": 2.0,
        }
    )


def new_fig(width: float = 7.0, height: float = 4.2) -> tuple[Any, Any]:
    apply_style()
    return plt.subplots(figsize=(width, height))
