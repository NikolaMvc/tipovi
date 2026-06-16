"""football-data.org (v4) provider — the reliable structured backbone.

Free tier covers the major leagues (PL, PD, SA, BL1, FL1, CL, ...). Requires a
free API key in FOOTBALL_DATA_API_KEY. When no key is configured every method
returns empty results so the pipeline degrades to FlashScore.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.config import settings
from backend.schemas import (
    MatchInput, TeamData, TeamSeasonStats, FormEntry, H2HData, LeagueAverages,
)
from backend.scraper.utils import fetch_json, normalize_team_name, log

BASE = "https://api.football-data.org/v4"
# Free-tier competitions worth scanning for upcoming fixtures.
DEFAULT_COMPETITIONS = ["PL", "PD", "SA", "BL1", "FL1", "DED", "PPL", "CL"]


class FootballDataClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.FOOTBALL_DATA_API_KEY
        self._standings_cache: dict[str, dict] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: Optional[dict] = None):
        if not self.enabled:
            return None
        data = fetch_json(f"{BASE}{path}", headers={"X-Auth-Token": self.api_key}, params=params)
        # crude rate-limit courtesy for the free tier (10 req/min)
        time.sleep(6.5)
        return data

    # ------------------------------------------------------------------ #
    UPCOMING_STATUSES = {"SCHEDULED", "TIMED"}

    def list_upcoming(self, days: int = 3, competitions: Optional[list[str]] = None) -> list[dict]:
        """Primary: the global /v4/matches endpoint (one request, every competition
        in the plan). Falls back to per-competition calls if the global endpoint
        returns nothing."""
        if not self.enabled:
            return []
        today = datetime.now(timezone.utc).date()
        date_from = today.isoformat()
        date_to = (today + timedelta(days=days)).isoformat()

        # --- Global endpoint (single call, respects the 10 req/min limit best) ---
        data = self._get("/matches", params={"dateFrom": date_from, "dateTo": date_to})
        out: list[dict] = []
        if data and data.get("matches"):
            out = [m for m in data["matches"] if m.get("status") in self.UPCOMING_STATUSES]
            log.info("football-data /v4/matches: %d upcoming fixtures (%s..%s)",
                     len(out), date_from, date_to)

        # --- Fallback: per-competition scan ---
        if not out:
            for code in (competitions or DEFAULT_COMPETITIONS):
                d = self._get(f"/competitions/{code}/matches",
                              params={"status": "SCHEDULED", "dateFrom": date_from, "dateTo": date_to})
                if d and d.get("matches"):
                    out.extend(d["matches"])
            log.info("football-data per-competition fallback: %d fixtures", len(out))
        return out

    def finished_results(self, days_back: int = 3) -> list[dict]:
        """Finished matches over the last N days (for settling tips)."""
        if not self.enabled:
            return []
        today = datetime.now(timezone.utc).date()
        date_from = (today - timedelta(days=days_back)).isoformat()
        date_to = today.isoformat()
        data = self._get("/matches", params={"dateFrom": date_from, "dateTo": date_to,
                                             "status": "FINISHED"})
        return data.get("matches", []) if data else []

    def standings(self, competition_code: str) -> Optional[dict]:
        if competition_code in self._standings_cache:
            return self._standings_cache[competition_code]
        data = self._get(f"/competitions/{competition_code}/standings")
        if data:
            self._standings_cache[competition_code] = data
        return data

    def team_last_matches(self, team_id: int, limit: int = 10) -> list[dict]:
        data = self._get(f"/teams/{team_id}/matches",
                         params={"status": "FINISHED", "limit": limit})
        return data.get("matches", []) if data else []

    def head2head(self, match_id: int) -> Optional[dict]:
        return self._get(f"/matches/{match_id}/head2head", params={"limit": 10})

    def match(self, match_id: int) -> Optional[dict]:
        data = self._get(f"/matches/{match_id}")
        return data.get("match") if data and "match" in data else data

    # ------------------------------------------------------------------ #
    # Mapping helpers
    # ------------------------------------------------------------------ #
    def _season_stats_from_standings(self, standings_data: Optional[dict], team_id: int):
        """Return (TeamSeasonStats, LeagueAverages) derived from HOME/AWAY/TOTAL tables."""
        season = TeamSeasonStats()
        if not standings_data:
            return season, None
        tables = {s.get("type"): s.get("table", []) for s in standings_data.get("standings", [])}

        def row(table_type):
            for r in tables.get(table_type, []):
                if r.get("team", {}).get("id") == team_id:
                    return r
            return None

        total, home, away = row("TOTAL"), row("HOME"), row("AWAY")
        if total:
            season.matches_played = total.get("playedGames", 0)
            season.position = total.get("position")
            season.points = total.get("points")
        if home and home.get("playedGames"):
            season.avg_scored_home = home["goalsFor"] / home["playedGames"]
            season.avg_conceded_home = home["goalsAgainst"] / home["playedGames"]
        if away and away.get("playedGames"):
            season.avg_scored_away = away["goalsFor"] / away["playedGames"]
            season.avg_conceded_away = away["goalsAgainst"] / away["playedGames"]

        league = self._league_averages(tables)
        return season, league

    @staticmethod
    def _league_averages(tables: dict) -> Optional[LeagueAverages]:
        home_rows = tables.get("HOME", [])
        away_rows = tables.get("AWAY", [])
        if not home_rows or not away_rows:
            return None
        hp = sum(r.get("playedGames", 0) for r in home_rows)
        ap = sum(r.get("playedGames", 0) for r in away_rows)
        if hp == 0 or ap == 0:
            return None
        home_goals = sum(r.get("goalsFor", 0) for r in home_rows)
        away_goals = sum(r.get("goalsFor", 0) for r in away_rows)
        return LeagueAverages(
            avg_home_goals=home_goals / hp,
            avg_away_goals=away_goals / ap,
            avg_scored_home=home_goals / hp,
            avg_scored_away=away_goals / ap,
            avg_conceded_home=away_goals / ap,   # what home sides concede == away goals
            avg_conceded_away=home_goals / hp,
            is_default=False,
        )

    @staticmethod
    def _form_from_matches(matches: list[dict], team_id: int) -> tuple[list[FormEntry], Optional[datetime]]:
        entries: list[FormEntry] = []
        last_date: Optional[datetime] = None
        # API returns oldest->newest; we want newest first
        for mt in sorted(matches, key=lambda x: x.get("utcDate", ""), reverse=True):
            score = mt.get("score", {}).get("fullTime", {})
            h, a = score.get("home"), score.get("away")
            if h is None or a is None:
                continue
            is_home = mt.get("homeTeam", {}).get("id") == team_id
            gf, ga = (h, a) if is_home else (a, h)
            opp = mt.get("awayTeam" if is_home else "homeTeam", {}).get("name", "")
            dt = None
            try:
                dt = datetime.fromisoformat(mt["utcDate"].replace("Z", "+00:00"))
            except Exception:
                pass
            if dt and last_date is None:
                last_date = dt
            entries.append(FormEntry(
                date=mt.get("utcDate"), opponent=opp, is_home=is_home,
                goals_for=gf, goals_against=ga,
            ))
        return entries, last_date

    def build_match_input(self, fixture: dict) -> MatchInput:
        """Convert a football-data fixture into a populated MatchInput."""
        comp = fixture.get("competition", {})
        code = comp.get("code", "")
        home_t = fixture.get("homeTeam", {})
        away_t = fixture.get("awayTeam", {})
        home_id, away_id = home_t.get("id"), away_t.get("id")

        match_date = None
        try:
            match_date = datetime.fromisoformat(fixture["utcDate"].replace("Z", "+00:00"))
        except Exception:
            pass

        standings = self.standings(code) if code else None
        home_season, league = self._season_stats_from_standings(standings, home_id)
        away_season, _ = self._season_stats_from_standings(standings, away_id)

        home_matches = self.team_last_matches(home_id) if home_id else []
        away_matches = self.team_last_matches(away_id) if away_id else []
        home_form, home_last = self._form_from_matches(home_matches, home_id)
        away_form, away_last = self._form_from_matches(away_matches, away_id)

        h2h = H2HData()
        if fixture.get("id"):
            h2h_data = self.head2head(fixture["id"])
            if h2h_data and "aggregates" in h2h_data:
                agg = h2h_data["aggregates"]
                ht = agg.get("homeTeam", {})
                at = agg.get("awayTeam", {})
                h2h = H2HData(
                    home_wins=ht.get("wins", 0),
                    draws=ht.get("draws", 0),
                    away_wins=at.get("wins", 0),
                    matches=agg.get("numberOfMatches", 0),
                )

        home = TeamData(name=home_t.get("name", ""), team_id=str(home_id),
                        season=home_season, recent=home_form, last_match_date=home_last)
        away = TeamData(name=away_t.get("name", ""), team_id=str(away_id),
                        season=away_season, recent=away_form, last_match_date=away_last)

        return MatchInput(
            home_team=home_t.get("name", ""),
            away_team=away_t.get("name", ""),
            league=comp.get("name", ""),
            match_date=match_date,
            venue=fixture.get("venue") or "",
            event_id=str(fixture.get("id")) if fixture.get("id") else None,
            home=home, away=away,
            league_avgs=league or LeagueAverages(),
            h2h=h2h,
            data_sources=["football-data.org"],
        )
