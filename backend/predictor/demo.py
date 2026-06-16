"""Run a full sample prediction and print the response payload.

    python -m backend.predictor.demo
"""
from __future__ import annotations

import json
from datetime import datetime

from backend.schemas import (
    MatchInput, TeamData, TeamSeasonStats, FormEntry, H2HData,
    RefereeData, WeatherData, OddsData, LeagueAverages,
)
from backend.predictor.engine import predict


def sample_match() -> MatchInput:
    home = TeamData(
        name="Manchester City",
        season=TeamSeasonStats(avg_scored_home=2.4, avg_scored_away=1.9,
                               avg_conceded_home=0.8, avg_conceded_away=1.1,
                               avg_xg=2.1, avg_xga=0.9, position=1, points=45),
        recent=[FormEntry(goals_for=g, goals_against=c) for g, c in
                [(3, 0), (2, 1), (1, 1), (0, 1), (4, 2)]],
        last_match_date=datetime(2026, 6, 10), lineup_known=True,
    )
    away = TeamData(
        name="Arsenal",
        season=TeamSeasonStats(avg_scored_home=1.9, avg_scored_away=1.4,
                               avg_conceded_home=1.0, avg_conceded_away=1.3,
                               avg_xg=1.7, avg_xga=1.1, position=2, points=42),
        recent=[FormEntry(goals_for=g, goals_against=c) for g, c in
                [(1, 0), (2, 2), (0, 1), (3, 1), (1, 1)]],
        last_match_date=datetime(2026, 6, 13), lineup_known=True,
    )
    return MatchInput(
        home_team="Manchester City", away_team="Arsenal", league="Premier League",
        match_date=datetime(2026, 6, 16), venue="Etihad Stadium",
        home=home, away=away, league_avgs=LeagueAverages(is_default=False),
        h2h=H2HData(home_wins=4, draws=3, away_wins=3, avg_goals=2.8, matches=10),
        referee=RefereeData(name="Mike Dean", avg_cards=4.2, avg_penalties=0.3),
        weather=WeatherData(temp=18, conditions="Clear", wind_speed=3, gol_suppressing=False),
        odds=OddsData(home=1.7, draw=4.0, away=4.5, over_2_5=1.8, under_2_5=2.0,
                      btts_yes=1.85, btts_no=1.95),
        data_sources=["demo"],
    )


if __name__ == "__main__":
    out = predict(sample_match())
    print(json.dumps(out, indent=2, default=str))
