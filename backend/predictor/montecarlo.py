"""Monte-Carlo match simulation (default 10,000 runs).

On top of the base Poisson goal draws it layers stochastic in-match events:
red cards (driven by referee card tendency), penalties (referee penalty
tendency) and fatigue-driven late goals. Fully reproducible when a seed is given.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class MonteCarloResult:
    simulations: int
    home_win: float
    draw: float
    away_win: float
    over_2_5: float
    under_2_5: float
    btts_yes: float
    std_home_goals: float
    std_away_goals: float
    confidence_interval: str   # e.g. "±1.8%"
    ci_half_width: float
    top_scores: list = field(default_factory=list)        # [{"score","prob"}]
    histogram: dict = field(default_factory=dict)          # total goals -> %
    mean_home_goals: float = 0.0
    mean_away_goals: float = 0.0


def simulate(
    lambda_home: float,
    lambda_away: float,
    n: int = 10000,
    *,
    referee_avg_cards: Optional[float] = None,
    referee_avg_penalties: Optional[float] = None,
    home_high_fatigue: bool = False,
    away_high_fatigue: bool = False,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    rng = np.random.default_rng(seed)

    lam_h = np.full(n, float(lambda_home))
    lam_a = np.full(n, float(lambda_away))

    # --- Red cards: a sent-off team scores at 0.75x ---
    if referee_avg_cards is not None:
        # ~ probability that *a* red card happens to a given team this match
        p_red = np.clip(referee_avg_cards / 50.0, 0.0, 0.12)
        lam_h = np.where(rng.random(n) < p_red, lam_h * 0.75, lam_h)
        lam_a = np.where(rng.random(n) < p_red, lam_a * 0.75, lam_a)

    home_goals = rng.poisson(lam_h)
    away_goals = rng.poisson(lam_a)

    # --- Penalties: converts at 78% ---
    if referee_avg_penalties is not None and referee_avg_penalties > 0:
        p_pen = np.clip(referee_avg_penalties, 0.0, 0.9)
        pen_event = rng.random(n) < p_pen
        to_home = rng.random(n) < 0.5
        converts = rng.random(n) < 0.78
        home_goals += (pen_event & to_home & converts).astype(int)
        away_goals += (pen_event & ~to_home & converts).astype(int)

    # --- Fatigue: tired team more likely to concede a late goal ---
    if home_high_fatigue:
        away_goals += (rng.random(n) < 0.08).astype(int)
    if away_high_fatigue:
        home_goals += (rng.random(n) < 0.08).astype(int)

    home_w = int(np.sum(home_goals > away_goals))
    away_w = int(np.sum(away_goals > home_goals))
    draws = n - home_w - away_w
    totals = home_goals + away_goals
    over = int(np.sum(totals >= 3))
    btts = int(np.sum((home_goals >= 1) & (away_goals >= 1)))

    # 95% CI half-width for the home-win proportion (binomial normal approx)
    p = home_w / n
    ci_half = 1.96 * float(np.sqrt(p * (1 - p) / n)) * 100

    # Top scorelines
    pairs, counts = np.unique(
        np.stack([np.minimum(home_goals, 9), np.minimum(away_goals, 9)], axis=1),
        axis=0, return_counts=True,
    )
    order = np.argsort(-counts)
    top = [
        {"score": f"{int(pairs[i][0])}-{int(pairs[i][1])}", "prob": round(counts[i] / n * 100, 2)}
        for i in order[:5]
    ]

    hist_vals, hist_counts = np.unique(np.minimum(totals, 8), return_counts=True)
    histogram = {int(v): round(c / n * 100, 2) for v, c in zip(hist_vals, hist_counts)}

    return MonteCarloResult(
        simulations=n,
        home_win=round(home_w / n * 100, 2),
        draw=round(draws / n * 100, 2),
        away_win=round(away_w / n * 100, 2),
        over_2_5=round(over / n * 100, 2),
        under_2_5=round((n - over) / n * 100, 2),
        btts_yes=round(btts / n * 100, 2),
        std_home_goals=round(float(np.std(home_goals)), 3),
        std_away_goals=round(float(np.std(away_goals)), 3),
        confidence_interval=f"±{ci_half:.1f}%",
        ci_half_width=round(ci_half, 3),
        top_scores=top,
        histogram=histogram,
        mean_home_goals=round(float(np.mean(home_goals)), 3),
        mean_away_goals=round(float(np.mean(away_goals)), 3),
    )
