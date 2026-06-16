"""Offline tests for the football-data.org mapping logic (no network)."""
from __future__ import annotations

from backend.scraper.footballdata import FootballDataClient


FIXTURE = {
    "id": 12345,
    "utcDate": "2026-06-18T19:00:00Z",
    "competition": {"code": "PL", "name": "Premier League"},
    "homeTeam": {"id": 65, "name": "Manchester City"},
    "awayTeam": {"id": 57, "name": "Arsenal"},
    "venue": "Etihad Stadium",
}

STANDINGS = {
    "standings": [
        {"type": "TOTAL", "table": [
            {"team": {"id": 65}, "position": 1, "points": 45, "playedGames": 19},
            {"team": {"id": 57}, "position": 2, "points": 42, "playedGames": 19},
        ]},
        {"type": "HOME", "table": [
            {"team": {"id": 65}, "playedGames": 10, "goalsFor": 24, "goalsAgainst": 8},
            {"team": {"id": 57}, "playedGames": 9, "goalsFor": 18, "goalsAgainst": 9},
        ]},
        {"type": "AWAY", "table": [
            {"team": {"id": 65}, "playedGames": 9, "goalsFor": 17, "goalsAgainst": 10},
            {"team": {"id": 57}, "playedGames": 10, "goalsFor": 14, "goalsAgainst": 13},
        ]},
    ]
}

HOME_MATCHES = {
    "matches": [
        {"utcDate": "2026-06-01T15:00:00Z", "homeTeam": {"id": 65, "name": "Manchester City"},
         "awayTeam": {"id": 1, "name": "A"}, "score": {"fullTime": {"home": 3, "away": 0}}},
        {"utcDate": "2026-06-08T15:00:00Z", "homeTeam": {"id": 2, "name": "B"},
         "awayTeam": {"id": 65, "name": "Manchester City"}, "score": {"fullTime": {"home": 1, "away": 2}}},
    ]
}


def _client_with_mocks():
    c = FootballDataClient(api_key="TEST")  # enabled

    def fake_get(path, params=None):
        if "standings" in path:
            return STANDINGS
        if "/teams/" in path and "/matches" in path:
            return HOME_MATCHES
        if "head2head" in path:
            return {"aggregates": {"numberOfMatches": 6,
                                   "homeTeam": {"wins": 3, "draws": 1},
                                   "awayTeam": {"wins": 2}}}
        return None

    c._get = fake_get  # type: ignore
    return c


def test_build_match_input_full():
    c = _client_with_mocks()
    m = c.build_match_input(FIXTURE)
    assert m.home_team == "Manchester City" and m.away_team == "Arsenal"
    assert m.league == "Premier League"
    assert m.venue == "Etihad Stadium"
    # season stats derived from HOME/AWAY tables
    assert round(m.home.season.avg_scored_home, 2) == 2.4   # 24/10
    assert round(m.home.season.avg_conceded_home, 2) == 0.8  # 8/10
    assert m.home.season.position == 1 and m.home.season.points == 45
    # league averages computed, not default
    assert m.league_avgs.is_default is False
    # form parsed newest-first
    assert m.home.last_n_results(5) == ["W", "W"]
    assert m.home.last_match_date is not None
    # h2h aggregates
    assert m.h2h.matches == 6 and m.h2h.home_wins == 3


def test_predict_on_built_input_runs():
    from backend.predictor.engine import predict
    c = _client_with_mocks()
    m = c.build_match_input(FIXTURE)
    out = predict(m)
    assert out["prediction"]["predicted_outcome"] in ("HOME_WIN", "DRAW", "AWAY_WIN")
    assert out["poisson_matrix_sum"] == __import__("pytest").approx(100.0, abs=0.5)
