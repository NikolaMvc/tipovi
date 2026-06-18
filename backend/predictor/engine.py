"""Prediction engine: ties lambda -> Poisson -> Monte-Carlo -> blend -> value
into the response payload described in the spec (Step 11)."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.config import settings
from backend.schemas import MatchInput, TeamData
from backend.predictor.lambda_calc import compute_lambdas, CONFIDENCE_FACTORS
from backend.predictor.poisson import compute_poisson
from backend.predictor.montecarlo import simulate
from backend.predictor.value import find_value_bets


# Weighted confidence: the genuinely predictive factors (form, xG, H2H, fatigue)
# carry most of the weight; the hard-to-get real facts (injuries/referee/weather)
# only refine it. A proxy xG is discounted so it can never fake a HIGH badge.
_FACTOR_WEIGHTS = {
    "form": 0.24, "xg": 0.24, "h2h": 0.16, "fatigue": 0.12,
    "injuries": 0.10, "referee": 0.07, "weather": 0.07,
}
_XG_PROXY_DISCOUNT = 0.6


def _confidence(available: set, xg_proxy: bool = False) -> tuple[str, int]:
    score = 0.0
    for f in CONFIDENCE_FACTORS:
        if f in available:
            w = _FACTOR_WEIGHTS.get(f, 0.0)
            if f == "xg" and xg_proxy:
                w *= _XG_PROXY_DISCOUNT
            score += w
    pct = round(score * 100)
    if pct >= 72:
        return "HIGH", pct
    if pct >= 48:
        return "MEDIUM", pct
    return "LOW", max(10, pct)


def _fatigue_status(rest_days):
    if rest_days is None:
        return "UNKNOWN"
    if rest_days >= 5:
        return "FRESH"
    if rest_days >= 4:
        return "NORMAL"
    return "TIRED"


def _form_pct(team: TeamData) -> int | None:
    res = team.last_n_results(5)
    if not res:
        return None
    pts = {"W": 1.0, "D": 0.5, "L": 0.0}
    weights = [5, 4, 3, 2, 1]
    num = sum(pts[r] * w for r, w in zip(res, weights))
    den = sum(weights[: len(res)])
    return round(num / den * 100) if den else None


def predict(m: MatchInput) -> dict:
    lam = compute_lambdas(m)
    pois = compute_poisson(lam.lambda_home, lam.lambda_away)

    h_rest = m.rest_days(m.home)
    a_rest = m.rest_days(m.away)
    mc = simulate(
        lam.lambda_home, lam.lambda_away,
        n=settings.MC_SIMULATIONS,
        referee_avg_cards=m.referee.avg_cards if m.referee else None,
        referee_avg_penalties=m.referee.avg_penalties if m.referee else None,
        home_high_fatigue=(h_rest is not None and h_rest < 3),
        away_high_fatigue=(a_rest is not None and a_rest < 3),
        seed=settings.mc_seed,
    )

    # --- Blend Poisson + Monte Carlo for stability ---
    home_win = round((pois.home_win + mc.home_win) / 2, 2)
    draw = round((pois.draw + mc.draw) / 2, 2)
    away_win = round((pois.away_win + mc.away_win) / 2, 2)
    over = round((pois.over_2_5 + mc.over_2_5) / 2, 2)
    under = round(100 - over, 2)
    btts_yes = round((pois.btts_yes + mc.btts_yes) / 2, 2)
    btts_no = round(100 - btts_yes, 2)

    outcomes = {"HOME_WIN": home_win, "DRAW": draw, "AWAY_WIN": away_win}
    predicted_outcome = max(outcomes, key=outcomes.get)

    xg_proxy = m.home.xg_source in ("proxy", "goals") or m.away.xg_source in ("proxy", "goals")
    confidence, confidence_score = _confidence(lam.available, xg_proxy=xg_proxy)

    markets_probs = {
        "home_win": home_win, "draw": draw, "away_win": away_win,
        "over_2_5": over, "under_2_5": under, "btts_yes": btts_yes, "btts_no": btts_no,
    }
    value_bets = find_value_bets(markets_probs, m.odds)

    def implied(odd):
        return round(1 / odd * 100, 2) if odd and odd > 1 else None

    response = {
        "match": {
            "home_team": m.home_team,
            "away_team": m.away_team,
            "league": m.league,
            "date": m.match_date.isoformat() if m.match_date else None,
            "venue": m.venue,
            "status": "UPCOMING",
        },
        "prediction": {
            "home_win_prob": home_win,
            "draw_prob": draw,
            "away_win_prob": away_win,
            "predicted_outcome": predicted_outcome,
            "confidence": confidence,
            "confidence_score": confidence_score,
            "missing_data": lam.missing,
            "proxy_factors": (["xg"] if (m.home.xg_source in ("proxy", "goals")
                                         or m.away.xg_source in ("proxy", "goals")) else []),
            "lambda": {"home": lam.lambda_home, "away": lam.lambda_away},
            "predicted_goals": {"home": mc.mean_home_goals, "away": mc.mean_away_goals},
            "most_likely_scores": pois.most_likely_scores,
            "monte_carlo": {
                "simulations": mc.simulations,
                "home_win": mc.home_win,
                "draw": mc.draw,
                "away_win": mc.away_win,
                "confidence_interval": mc.confidence_interval,
                "histogram": mc.histogram,
                "top_scores": mc.top_scores,
            },
        },
        "markets": {
            "over_under_2_5": {"over": over, "under": under},
            "btts": {"yes": btts_yes, "no": btts_no},
        },
        "value_bets": value_bets,
        "breakdown": {
            "form": {
                "home_last5": m.home.last_n_results(5),
                "away_last5": m.away.last_n_results(5),
                "home_form_score": _form_pct(m.home),
                "away_form_score": _form_pct(m.away),
            },
            "h2h": {
                "home_wins": m.h2h.home_wins,
                "draws": m.h2h.draws,
                "away_wins": m.h2h.away_wins,
                "avg_goals": m.h2h.avg_goals,
                "matches": m.h2h.matches,
            } if m.h2h else None,
            "xg": {
                "home_xg": m.home.season.avg_xg,
                "home_xga": m.home.season.avg_xga,
                "away_xg": m.away.season.avg_xg,
                "away_xga": m.away.season.avg_xga,
                # provenance: "real" (FlashScore xG) | "proxy" (from shots) | "goals"
                "home_source": m.home.xg_source,
                "away_source": m.away.xg_source,
                "is_proxy": (m.home.xg_source in ("proxy", "goals")
                             or m.away.xg_source in ("proxy", "goals")),
            },
            "standings": {
                "home_pos": m.home.season.position,
                "away_pos": m.away.season.position,
                "points_diff": (
                    abs(m.home.season.points - m.away.season.points)
                    if m.home.season.points is not None and m.away.season.points is not None
                    else None
                ),
            },
            "injuries": {
                "home_missing": m.home.missing_players,
                "away_missing": m.away.missing_players,
            },
            "referee": {
                "name": m.referee.name,
                "avg_cards": m.referee.avg_cards,
                "avg_penalties": m.referee.avg_penalties,
            } if m.referee else None,
            "fatigue": {
                "home_rest_days": h_rest,
                "away_rest_days": a_rest,
                "home_status": _fatigue_status(h_rest),
                "away_status": _fatigue_status(a_rest),
            },
            "weather": {
                "temp": m.weather.temp,
                "conditions": m.weather.conditions,
                "wind_speed": m.weather.wind_speed,
                "gol_suppressing": m.weather.gol_suppressing,
            } if m.weather else None,
            "factors_used": lam.factors,
            "positions_estimated": lam.positions_estimated,
            "notes": lam.notes,
        },
        "poisson_matrix": pois.matrix,
        "poisson_matrix_sum": pois.matrix_sum,
        "implied_probs": {
            "home": implied(m.odds.home) if m.odds else None,
            "draw": implied(m.odds.draw) if m.odds else None,
            "away": implied(m.odds.away) if m.odds else None,
        },
        "data_sources": m.data_sources,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    return response
