"""Unit tests for the deterministic predictor core."""
from __future__ import annotations

from datetime import datetime

import pytest

from backend.schemas import (
    MatchInput, TeamData, TeamSeasonStats, FormEntry, H2HData,
    RefereeData, WeatherData, OddsData, LeagueAverages,
)
from backend.predictor.lambda_calc import compute_lambdas
from backend.predictor.poisson import compute_poisson
from backend.predictor.montecarlo import simulate
from backend.predictor.engine import predict
from backend.predictor.value import evaluate, find_value_bets


def _full_match() -> MatchInput:
    home = TeamData(
        name="Manchester City", team_id="1",
        season=TeamSeasonStats(
            matches_played=19, avg_scored_home=2.4, avg_scored_away=1.9,
            avg_conceded_home=0.8, avg_conceded_away=1.1, avg_xg=2.1, avg_xga=0.9,
            position=1, points=45,
        ),
        recent=[
            FormEntry(opponent="A", is_home=True, goals_for=3, goals_against=0),
            FormEntry(opponent="B", is_home=False, goals_for=2, goals_against=1),
            FormEntry(opponent="C", is_home=True, goals_for=1, goals_against=1),
            FormEntry(opponent="D", is_home=False, goals_for=0, goals_against=1),
            FormEntry(opponent="E", is_home=True, goals_for=4, goals_against=2),
        ],
        last_match_date=datetime(2026, 6, 10),
        lineup_known=True,
    )
    away = TeamData(
        name="Arsenal", team_id="2",
        season=TeamSeasonStats(
            matches_played=19, avg_scored_home=1.9, avg_scored_away=1.4,
            avg_conceded_home=1.0, avg_conceded_away=1.3, avg_xg=1.7, avg_xga=1.1,
            position=2, points=42,
        ),
        recent=[
            FormEntry(opponent="F", is_home=False, goals_for=1, goals_against=0),
            FormEntry(opponent="G", is_home=True, goals_for=2, goals_against=2),
            FormEntry(opponent="H", is_home=False, goals_for=0, goals_against=1),
            FormEntry(opponent="I", is_home=True, goals_for=3, goals_against=1),
            FormEntry(opponent="J", is_home=False, goals_for=1, goals_against=1),
        ],
        last_match_date=datetime(2026, 6, 13),
        lineup_known=True,
    )
    return MatchInput(
        home_team="Manchester City", away_team="Arsenal", league="Premier League",
        match_date=datetime(2026, 6, 16), venue="Etihad Stadium", event_id="999",
        home=home, away=away,
        league_avgs=LeagueAverages(is_default=False),
        h2h=H2HData(home_wins=4, draws=3, away_wins=3, avg_goals=2.8, matches=10),
        referee=RefereeData(name="Mike Dean", avg_cards=4.2, avg_penalties=0.3),
        weather=WeatherData(temp=18, conditions="Clear", wind_speed=3, gol_suppressing=False),
        odds=OddsData(home=1.7, draw=4.0, away=4.5, over_2_5=1.8, under_2_5=2.0,
                      btts_yes=1.85, btts_no=1.95),
        data_sources=["flashscore", "footballdata"],
    )


# --- Lambda ---

def test_lambda_positive_and_home_advantage():
    res = compute_lambdas(_full_match())
    assert res.lambda_home > 0 and res.lambda_away > 0
    assert res.lambda_home > res.lambda_away  # strong home favourite
    assert res.missing == []  # all 7 factors present


def test_lambda_graceful_with_empty_match():
    res = compute_lambdas(MatchInput(home_team="X", away_team="Y"))
    assert res.lambda_home > 0 and res.lambda_away > 0
    assert set(res.missing) == set(
        ["form", "h2h", "xg", "injuries", "referee", "weather", "fatigue"]
    )


# --- Poisson ---

def test_poisson_matrix_sums_to_100():
    res = compute_poisson(1.72, 1.15)
    assert res.matrix_sum == pytest.approx(100.0, abs=0.5)
    total = sum(sum(row) for row in res.matrix)
    assert total == pytest.approx(100.0, abs=0.5)


def test_poisson_probabilities_consistent():
    res = compute_poisson(1.5, 1.2)
    assert res.home_win + res.draw + res.away_win == pytest.approx(100.0, abs=0.5)
    assert res.over_2_5 + res.under_2_5 == pytest.approx(100.0, abs=0.5)
    assert 0 <= res.btts_yes <= 100
    assert len(res.most_likely_scores) == 5


# --- Monte Carlo ---

def test_montecarlo_reproducible_with_seed():
    a = simulate(1.72, 1.15, n=10000, seed=42)
    b = simulate(1.72, 1.15, n=10000, seed=42)
    assert a.home_win == b.home_win
    assert a.draw == b.draw
    assert a.top_scores == b.top_scores


def test_montecarlo_sums_and_ci():
    res = simulate(1.6, 1.2, n=10000, seed=1)
    assert res.home_win + res.draw + res.away_win == pytest.approx(100.0, abs=0.5)
    assert res.ci_half_width > 0
    assert res.confidence_interval.startswith("±")


def test_montecarlo_matches_poisson_roughly():
    pois = compute_poisson(1.7, 1.1)
    mc = simulate(1.7, 1.1, n=20000, seed=7)
    # No special events -> MC should track Poisson within a few percent.
    assert abs(pois.home_win - mc.home_win) < 4


# --- Value ---

def test_value_bet_math():
    vb = evaluate("1X2", "Home Win", 60.0, 2.0)
    assert vb.implied_prob == pytest.approx(50.0)
    assert vb.value == pytest.approx(10.0)
    # kelly = (0.6*2 - 1)/(2-1) = 0.2 -> 20%
    assert vb.kelly_pct == pytest.approx(20.0)
    assert vb.half_kelly_pct == pytest.approx(10.0)
    assert vb.rating == "GOOD_VALUE"


def test_value_filters_negative():
    odds = OddsData(home=1.5, draw=4.0, away=6.0)
    bets = find_value_bets({"home_win": 40, "draw": 25, "away_win": 35}, odds)
    # home implied ~66.7% > our 40% -> negative, excluded
    assert all(b["value"] > 0 for b in bets)


# --- Engine ---

def test_engine_full_payload_shape():
    out = predict(_full_match())
    assert out["prediction"]["confidence"] == "HIGH"
    assert out["prediction"]["predicted_outcome"] in ("HOME_WIN", "DRAW", "AWAY_WIN")
    probs = out["prediction"]
    assert probs["home_win_prob"] + probs["draw_prob"] + probs["away_win_prob"] == pytest.approx(100.0, abs=1.0)
    assert len(out["poisson_matrix"]) == 7 and len(out["poisson_matrix"][0]) == 7
    assert out["data_sources"] == ["flashscore", "footballdata"]
    assert "value_bets" in out


def test_engine_degrades_without_data():
    out = predict(MatchInput(home_team="X", away_team="Y", match_date=datetime(2026, 6, 16)))
    assert out["prediction"]["confidence"] == "LOW"
    assert len(out["prediction"]["missing_data"]) >= 5
    assert out["value_bets"] == []  # no odds
