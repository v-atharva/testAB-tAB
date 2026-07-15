"""abkit: a small, tested experimentation-analysis toolkit.

Pure functions on counts (no I/O, no pandas): design, frequentist readout,
sequential (always-valid) inference, multiplicity control, empirical-Bayes
shrinkage, Bayesian readout, and experiment health checks — composed into a
decision-grade readout by :mod:`abkit.readout`.

Every statistical routine here is validated in ``tests/`` against simulation
(empirical type-I error, CI coverage, anytime error control) or a reference
implementation (statsmodels).
"""

from abkit import bayes, design, freq, health, multiplicity, readout, sequential, shrinkage

__all__ = [
    "bayes",
    "design",
    "freq",
    "health",
    "multiplicity",
    "readout",
    "sequential",
    "shrinkage",
]
