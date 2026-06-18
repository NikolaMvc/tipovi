"""Expected-goals (lambda) calculation — weighted-factor model.

Lambda is a weighted blend of six factors (weights sum to 100%):

    form              45%   table-position-aware scoring of the last 5 matches
    xg (proxy)        20%   FlashScore xG / shot-proxy / goals
    attack/defense    18%   goals scored/conceded strength vs the league
    home advantage     7%
    h2h                5%
    fatigue            5%

Each factor yields a multiplier centred on 1.0. The weighted average of the
multipliers (renormalised over whatever factors are available) scales the league
baseline into the team's lambda, so a missing factor simply drops out and the rest
are reweighted (graceful degradation). injuries / referee / weather are no longer
lambda inputs — they remain confidence factors and Monte-Carlo event drivers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.schemas import MatchInput, TeamData, FormEntry

# Confidence factors (unchanged — separate concern from the lambda weights).
CONFIDENCE_FACTORS = ["form", "h2h", "xg", "injuries", "referee", "weather", "fatigue"]

# Lambda factor weights (sum = 1.0).
LAMBDA_WEIGHTS = {
    "form": 0.45,
    "xg": 0.20,
    "attack_defense": 0.18,
    "home": 0.07,
    "h2h": 0.05,
    "fatigue": 0.05,
}

MID_TABLE_POSITION = 10  # fallback when an opponent's current position is unknown
LAMBDA_MIN, LAMBDA_MAX = 0.15, 4.5


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class LambdaResult:
    lambda_home: float
    lambda_away: float
    factors: dict = field(default_factory=dict)
    available: set = field(default_factory=set)        # CONFIDENCE_FACTORS we had
    missing: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    positions_estimated: int = 0                        # how many opponent positions we guessed


# --------------------------------------------------------------------------- #
# Form scoring (table-position aware)
# --------------------------------------------------------------------------- #
def form_match_points(outcome: str, is_home: bool, opp_pos: Optional[int]) -> int:
    """Points (0-3) for one historical match, by outcome + venue + opponent's
    CURRENT table position. ``is_home`` = where THAT team played in THAT match."""
    pos = MID_TABLE_POSITION if opp_pos is None else opp_pos
    if outcome == "W":
        if is_home:
            return 3 if pos <= 5 else 2
        return 3 if pos <= 8 else 2
    if outcome == "D":
        if is_home:
            return 1 if pos <= 8 else 0
        if pos <= 2:
            return 2
        if pos <= 14:
            return 1
        return 0
    if outcome == "L":
        if is_home:
            return 1 if pos <= 2 else 0
        return 1 if pos <= 8 else 0
    return 0


def compute_form_score(entries: list[FormEntry], n: int = 5):
    """Return (form_score 0..3, per-match details, n_estimated_positions).

    Uses up to ``n`` matches; the caller is expected to have already restricted to
    league matches for clubs."""
    sub = entries[:n]
    if not sub:
        return None, [], 0
    details = []
    total = 0
    estimated = 0
    for e in sub:
        pts = form_match_points(e.result, e.is_home, e.opponent_position)
        total += pts
        if e.opponent_position is None or e.position_estimated:
            estimated += 1
        details.append({
            "opponent": e.opponent,
            "position": e.opponent_position if e.opponent_position is not None else MID_TABLE_POSITION,
            "position_estimated": e.opponent_position is None or e.position_estimated,
            "venue": "home" if e.is_home else "away",
            "outcome": e.result,
            "score": f"{e.goals_for}-{e.goals_against}",
            "points": pts,
        })
    return total / len(sub), details, estimated


# --------------------------------------------------------------------------- #
# Per-factor multipliers (centred on 1.0)
# --------------------------------------------------------------------------- #
def _form_mult(score: Optional[float]) -> Optional[float]:
    if score is None:
        return None
    # 0..3 -> 0.70..1.30, neutral 1.5 -> 1.00
    return _clamp(0.70 + (score / 3.0) * 0.60, 0.70, 1.30)


def _xg_mult(team_xg: Optional[float], league_base: float) -> Optional[float]:
    if team_xg is None or league_base <= 0:
        return None
    return _clamp(team_xg / league_base, 0.70, 1.40)


def _attack_defense_mult(attack_scored: Optional[float], league_scored: float,
                         opp_conceded: Optional[float], league_conceded: float) -> Optional[float]:
    if attack_scored is None and opp_conceded is None:
        return None
    atk = _clamp(attack_scored / league_scored, 0.4, 2.2) if (attack_scored and league_scored > 0) else 1.0
    dfn = _clamp(opp_conceded / league_conceded, 0.4, 2.2) if (opp_conceded and league_conceded > 0) else 1.0
    return _clamp(atk * dfn, 0.6, 1.6)


def _h2h_mult(h2h, for_home: bool) -> Optional[float]:
    if not h2h or not h2h.matches:
        return None
    edge = (h2h.home_wins - h2h.away_wins) / h2h.matches
    if not for_home:
        edge = -edge
    return _clamp(1.0 + edge * 0.30, 0.85, 1.15)


def _fatigue_mult(rest_days: Optional[int]) -> Optional[float]:
    if rest_days is None:
        return None
    if rest_days < 3:
        return 0.92
    if rest_days <= 6:
        return 1.0
    return 1.02


def _combine(base: float, mults: dict) -> tuple[float, dict]:
    """Weighted blend of factor multipliers, renormalised over present factors.
    Returns (lambda, per-factor {weight, mult, contribution})."""
    present = {k: v for k, v in mults.items() if v is not None}
    wsum = sum(LAMBDA_WEIGHTS[k] for k in present) or 1.0
    combined = sum(LAMBDA_WEIGHTS[k] * v for k, v in present.items()) / wsum
    lam = base * combined
    detail = {}
    for k, v in present.items():
        w_norm = LAMBDA_WEIGHTS[k] / wsum
        detail[k] = {
            "weight": LAMBDA_WEIGHTS[k],
            "weight_norm": round(w_norm, 3),
            "mult": round(v, 3),
            "contribution": round(base * w_norm * (v - 1.0), 3),  # signed effect on lambda
        }
    return lam, detail


# --------------------------------------------------------------------------- #
def compute_lambdas(m: MatchInput) -> LambdaResult:
    avail: set[str] = set()
    notes: list[str] = []
    la = m.league_avgs
    base_home = la.avg_home_goals
    base_away = la.avg_away_goals

    # --- Form (table-position aware) ---
    home_form_entries = [e for e in m.home.recent if e.is_league] or m.home.recent
    away_form_entries = [e for e in m.away.recent if e.is_league] or m.away.recent
    hf_score, hf_details, hf_est = compute_form_score(home_form_entries)
    af_score, af_details, af_est = compute_form_score(away_form_entries)
    if hf_score is not None or af_score is not None:
        avail.add("form")

    # --- xG ---
    if m.home.season.avg_xg is not None or m.away.season.avg_xg is not None:
        avail.add("xg")

    # --- attack/defense availability ---
    have_ad = any(v is not None for v in (
        m.home.season.avg_scored_home, m.away.season.avg_scored_away,
        m.home.season.avg_conceded_home, m.away.season.avg_conceded_away))

    # --- h2h / fatigue ---
    if m.h2h and m.h2h.matches > 0:
        avail.add("h2h")
    h_rest, a_rest = m.rest_days(m.home), m.rest_days(m.away)
    if h_rest is not None or a_rest is not None:
        avail.add("fatigue")

    # Build per-team multiplier sets.
    home_mults = {
        "form": _form_mult(hf_score),
        "xg": _xg_mult(m.home.season.avg_xg, base_home),
        "attack_defense": _attack_defense_mult(
            m.home.season.avg_scored_home, la.avg_scored_home,
            m.away.season.avg_conceded_away, la.avg_conceded_away) if have_ad else None,
        "home": 1.20,  # home advantage (always present)
        "h2h": _h2h_mult(m.h2h, for_home=True),
        "fatigue": _fatigue_mult(h_rest),
    }
    away_mults = {
        "form": _form_mult(af_score),
        "xg": _xg_mult(m.away.season.avg_xg, base_away),
        "attack_defense": _attack_defense_mult(
            m.away.season.avg_scored_away, la.avg_scored_away,
            m.home.season.avg_conceded_home, la.avg_conceded_home) if have_ad else None,
        "home": 0.85,  # away penalty
        "h2h": _h2h_mult(m.h2h, for_home=False),
        "fatigue": _fatigue_mult(a_rest),
    }

    lam_home, home_detail = _combine(base_home, home_mults)
    lam_away, away_detail = _combine(base_away, away_mults)
    lam_home = _clamp(lam_home, LAMBDA_MIN, LAMBDA_MAX)
    lam_away = _clamp(lam_away, LAMBDA_MIN, LAMBDA_MAX)

    # --- confidence-only factors (no lambda effect) ---
    if m.referee is not None and (m.referee.avg_cards is not None or m.referee.avg_penalties is not None):
        avail.add("referee")
    if m.weather is not None and m.weather.conditions is not None:
        avail.add("weather")
    if m.home.lineup_known or m.away.lineup_known or m.home.missing_players or m.away.missing_players:
        avail.add("injuries")

    if not have_ad:
        notes.append("No season scoring stats; attack/defense factor dropped, weights renormalized.")
    positions_estimated = hf_est + af_est
    if positions_estimated:
        notes.append(f"{positions_estimated} opponent position(s) unknown -> mid-table estimate.")

    factors = {
        "weights": LAMBDA_WEIGHTS,
        "form": {
            "home_form_score": None if hf_score is None else round(hf_score, 3),
            "away_form_score": None if af_score is None else round(af_score, 3),
            "home_matches": hf_details,
            "away_matches": af_details,
        },
        "home_factors": home_detail,   # per-factor weight/mult/contribution for home lambda
        "away_factors": away_detail,
        "base": {"home_goals": base_home, "away_goals": base_away},
        "lambda": {"home": round(lam_home, 3), "away": round(lam_away, 3)},
    }

    return LambdaResult(
        lambda_home=round(lam_home, 4),
        lambda_away=round(lam_away, 4),
        factors=factors,
        available=avail,
        missing=[f for f in CONFIDENCE_FACTORS if f not in avail],
        notes=notes,
        positions_estimated=positions_estimated,
    )
