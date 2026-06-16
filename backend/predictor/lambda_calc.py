"""Expected-goals (lambda) calculation — Dixon-Coles style attack/defense
strengths plus situational modifiers.

The result feeds the Poisson and Monte-Carlo stages. Every modifier degrades
gracefully: when a data category is missing the modifier defaults to 1.0 and the
category is recorded in ``missing`` so the engine can lower the confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.schemas import MatchInput, TeamData

# The 7 factors that drive the confidence score (Step 5).
CONFIDENCE_FACTORS = ["form", "h2h", "xg", "injuries", "referee", "weather", "fatigue"]

LAMBDA_MIN, LAMBDA_MAX = 0.15, 4.5


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class LambdaResult:
    lambda_home: float
    lambda_away: float
    factors: dict = field(default_factory=dict)       # human-readable multipliers used
    available: set = field(default_factory=set)        # which CONFIDENCE_FACTORS we had
    missing: list = field(default_factory=list)        # which CONFIDENCE_FACTORS were absent
    notes: list = field(default_factory=list)


def _form_score(results: list[str]) -> Optional[float]:
    """Weighted form on last 5 (weights 5,4,3,2,1) -> 0..1."""
    if not results:
        return None
    weights = [5, 4, 3, 2, 1]
    pts = {"W": 1.0, "D": 0.5, "L": 0.0}
    num = den = 0.0
    for r, w in zip(results, weights):
        num += pts.get(r, 0.5) * w
        den += w
    return num / den if den else None


def _form_multiplier(score: Optional[float]) -> float:
    """Map a 0..1 form score onto the 0.85..1.15 multiplier band."""
    if score is None:
        return 1.0
    return _clamp(0.85 + score * 0.30, 0.85, 1.15)


def _attack_strength(avg_scored: Optional[float], league_avg: float) -> float:
    if avg_scored is None or league_avg <= 0:
        return 1.0
    return _clamp(avg_scored / league_avg, 0.3, 3.0)


def _defense_strength(avg_conceded: Optional[float], league_avg: float) -> float:
    if avg_conceded is None or league_avg <= 0:
        return 1.0
    return _clamp(avg_conceded / league_avg, 0.3, 3.0)


def _xg_correction(team: TeamData) -> float:
    """If a team scores fewer goals than its xG it has been unlucky -> nudge up;
    if it scores more than xG it has over-performed -> regress down."""
    xg = team.season.avg_xg
    scored = team.season.avg_scored_home or team.season.avg_scored_away
    if xg is None or scored is None or xg <= 0:
        return 1.0
    ratio = xg / scored  # >1 => underperforming finishing => expect upward regression
    return _clamp(0.90 + 0.10 * ratio, 0.92, 1.08)


def _fatigue_multiplier(rest_days: Optional[int]) -> float:
    if rest_days is None:
        return 1.0
    if rest_days < 3:
        return 0.92
    if rest_days <= 6:
        return 1.0
    return 1.02


def compute_lambdas(m: MatchInput) -> LambdaResult:
    avail: set[str] = set()
    factors: dict = {}
    notes: list[str] = []

    la = m.league_avgs

    # --- Base attack/defense (Dixon-Coles strengths) ---
    home_attack = _attack_strength(m.home.season.avg_scored_home, la.avg_scored_home)
    away_attack = _attack_strength(m.away.season.avg_scored_away, la.avg_scored_away)
    home_defense = _defense_strength(m.home.season.avg_conceded_home, la.avg_conceded_home)
    away_defense = _defense_strength(m.away.season.avg_conceded_away, la.avg_conceded_away)

    have_team_stats = any(
        v is not None
        for v in (
            m.home.season.avg_scored_home, m.away.season.avg_scored_away,
            m.home.season.avg_conceded_home, m.away.season.avg_conceded_away,
        )
    )
    if not have_team_stats:
        notes.append("No season scoring stats; using league baselines (strength=1.0).")

    lam_home = home_attack * away_defense * la.avg_home_goals
    lam_away = away_attack * home_defense * la.avg_away_goals
    factors["base"] = {
        "home_attack": round(home_attack, 3), "away_attack": round(away_attack, 3),
        "home_defense": round(home_defense, 3), "away_defense": round(away_defense, 3),
        "lambda_home": round(lam_home, 3), "lambda_away": round(lam_away, 3),
    }

    # --- 1. Form ---
    hf = _form_score(m.home.last_n_results(5))
    af = _form_score(m.away.last_n_results(5))
    if hf is not None or af is not None:
        avail.add("form")
    hf_mult, af_mult = _form_multiplier(hf), _form_multiplier(af)
    lam_home *= hf_mult
    lam_away *= af_mult
    factors["form"] = {
        "home_form_score": None if hf is None else round(hf * 100),
        "away_form_score": None if af is None else round(af * 100),
        "home_mult": round(hf_mult, 3), "away_mult": round(af_mult, 3),
    }

    # --- 2. xG correction ---
    if m.home.season.avg_xg is not None or m.away.season.avg_xg is not None:
        avail.add("xg")
    h_xg, a_xg = _xg_correction(m.home), _xg_correction(m.away)
    lam_home *= h_xg
    lam_away *= a_xg
    factors["xg"] = {"home_mult": round(h_xg, 3), "away_mult": round(a_xg, 3)}

    # --- 3. Fatigue ---
    h_rest = m.rest_days(m.home)
    a_rest = m.rest_days(m.away)
    if h_rest is not None or a_rest is not None:
        avail.add("fatigue")
    h_fat, a_fat = _fatigue_multiplier(h_rest), _fatigue_multiplier(a_rest)
    lam_home *= h_fat
    lam_away *= a_fat
    factors["fatigue"] = {
        "home_rest_days": h_rest, "away_rest_days": a_rest,
        "home_mult": round(h_fat, 3), "away_mult": round(a_fat, 3),
    }

    # --- 4. Injuries ---
    h_missing = m.home.missing_players or []
    a_missing = m.away.missing_players or []
    if m.home.lineup_known or m.away.lineup_known or h_missing or a_missing:
        avail.add("injuries")
    inj = {"home_attack_mult": 1.0, "away_attack_mult": 1.0,
           "home_concede_mult": 1.0, "away_concede_mult": 1.0}
    for p in h_missing:
        if p.get("key") and p.get("role") == "attacker":
            inj["home_attack_mult"] *= 0.90
        if p.get("key") and p.get("role") == "defender":
            inj["away_concede_mult"] *= 1.08  # home's opponents concede less? -> away scores more
    for p in a_missing:
        if p.get("key") and p.get("role") == "attacker":
            inj["away_attack_mult"] *= 0.90
        if p.get("key") and p.get("role") == "defender":
            inj["home_concede_mult"] *= 1.08
    lam_home *= inj["home_attack_mult"] * inj["home_concede_mult"]
    lam_away *= inj["away_attack_mult"] * inj["away_concede_mult"]
    factors["injuries"] = {k: round(v, 3) for k, v in inj.items()}

    # --- 5. Weather ---
    if m.weather is not None and m.weather.conditions is not None:
        avail.add("weather")
        if m.weather.gol_suppressing:
            lam_home *= 0.93
            lam_away *= 0.93
            factors["weather"] = {"gol_suppressing": True, "mult": 0.93}
        else:
            factors["weather"] = {"gol_suppressing": False, "mult": 1.0}

    # --- Referee + H2H availability (used downstream, not in lambda directly) ---
    if m.referee is not None and (m.referee.avg_cards is not None or m.referee.avg_penalties is not None):
        avail.add("referee")
    if m.h2h is not None and m.h2h.matches > 0:
        avail.add("h2h")

    lam_home = _clamp(lam_home, LAMBDA_MIN, LAMBDA_MAX)
    lam_away = _clamp(lam_away, LAMBDA_MIN, LAMBDA_MAX)

    missing = [f for f in CONFIDENCE_FACTORS if f not in avail]

    return LambdaResult(
        lambda_home=round(lam_home, 4),
        lambda_away=round(lam_away, 4),
        factors=factors,
        available=avail,
        missing=missing,
        notes=notes,
    )
