"""Multiple-testing corrections.

Two scopes are used in this project and must not be conflated:

* within a k-arm test — Holm (family-wise control) on the pairwise
  variant-vs-baseline p-values, so "ship X" claims control the chance of
  shipping any false winner within the experiment;
* across the corpus — Benjamini-Hochberg (FDR control) when scanning
  thousands of experiments for "significant" results.

Both return **adjusted p-values** (compare directly to alpha), validated
against ``statsmodels.stats.multitest.multipletests`` in tests.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _as_pvals(p_values: list[float] | NDArray[np.float64]) -> NDArray[np.float64]:
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("p_values must be a non-empty 1-D array")
    if np.any((p < 0) | (p > 1)) or np.any(np.isnan(p)):
        raise ValueError("p_values must be in [0, 1] and non-NaN")
    return p


def holm(p_values: list[float] | NDArray[np.float64]) -> NDArray[np.float64]:
    """Holm step-down adjusted p-values (family-wise error control)."""
    p = _as_pvals(p_values)
    m = p.size
    order = np.argsort(p)
    adj_sorted = np.maximum.accumulate((m - np.arange(m)) * p[order])
    adj = np.empty(m, dtype=np.float64)
    adj[order] = np.minimum(adj_sorted, 1.0)
    return adj


def benjamini_hochberg(p_values: list[float] | NDArray[np.float64]) -> NDArray[np.float64]:
    """Benjamini-Hochberg adjusted p-values (q-values; FDR control)."""
    p = _as_pvals(p_values)
    m = p.size
    order = np.argsort(p)
    ranked = p[order] * m / (np.arange(m) + 1)
    adj_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    adj = np.empty(m, dtype=np.float64)
    adj[order] = np.minimum(adj_sorted, 1.0)
    return adj
