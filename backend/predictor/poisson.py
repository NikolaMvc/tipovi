"""Poisson scoreline model with a Dixon-Coles low-score correction."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import poisson as sp_poisson

MAX_GOALS = 6  # matrix is (MAX_GOALS+1) x (MAX_GOALS+1) = 7x7
RHO = -0.13


def _marginal(lmbda: float) -> np.ndarray:
    """P(X=k) for k=0..MAX_GOALS, with the final bucket absorbing the tail so the
    vector sums to exactly 1."""
    ks = np.arange(0, MAX_GOALS + 1)
    p = sp_poisson.pmf(ks, lmbda)
    p[-1] = max(0.0, 1.0 - sp_poisson.cdf(MAX_GOALS - 1, lmbda))
    total = p.sum()
    return p / total if total > 0 else p


def _dc_tau(i: int, j: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles dependence adjustment for low scores."""
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


@dataclass
class PoissonResult:
    home_win: float
    draw: float
    away_win: float
    over_2_5: float
    under_2_5: float
    btts_yes: float
    btts_no: float
    most_likely_scores: list = field(default_factory=list)  # [{"score","prob"}]
    matrix: list = field(default_factory=list)              # 7x7 list of lists (%)
    matrix_sum: float = 0.0
    home_marginal: list = field(default_factory=list)
    away_marginal: list = field(default_factory=list)


def compute_poisson(lambda_home: float, lambda_away: float, rho: float = RHO) -> PoissonResult:
    ph = _marginal(lambda_home)
    pa = _marginal(lambda_away)

    matrix = np.outer(ph, pa)  # matrix[i][j] = P(home=i) * P(away=j)

    # Dixon-Coles correction on the four low-score cells.
    for i in (0, 1):
        for j in (0, 1):
            matrix[i][j] *= _dc_tau(i, j, lambda_home, lambda_away, rho)

    total = matrix.sum()
    if total > 0:
        matrix = matrix / total  # renormalize after the DC adjustment

    # --- Derive markets ---
    home_win = float(np.tril(matrix, -1).sum())   # home > away
    away_win = float(np.triu(matrix, 1).sum())    # away > home
    draw = float(np.trace(matrix))

    over = 0.0
    btts = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            if i + j >= 3:
                over += matrix[i][j]
            if i >= 1 and j >= 1:
                btts += matrix[i][j]

    # Top scorelines
    flat = [
        {"score": f"{i}-{j}", "prob": round(float(matrix[i][j]) * 100, 2)}
        for i in range(MAX_GOALS + 1) for j in range(MAX_GOALS + 1)
    ]
    flat.sort(key=lambda x: x["prob"], reverse=True)

    return PoissonResult(
        home_win=round(home_win * 100, 2),
        draw=round(draw * 100, 2),
        away_win=round(away_win * 100, 2),
        over_2_5=round(over * 100, 2),
        under_2_5=round((1 - over) * 100, 2),
        btts_yes=round(btts * 100, 2),
        btts_no=round((1 - btts) * 100, 2),
        most_likely_scores=flat[:5],
        matrix=[[round(float(matrix[i][j]) * 100, 3) for j in range(MAX_GOALS + 1)]
                for i in range(MAX_GOALS + 1)],
        matrix_sum=round(float(matrix.sum()) * 100, 4),
        home_marginal=[round(float(x) * 100, 3) for x in ph],
        away_marginal=[round(float(x) * 100, 3) for x in pa],
    )
