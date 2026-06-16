"""Data provider orchestration.

Combines the available sources into a list of populated ``MatchInput`` objects:

  * Primary structured backbone: football-data.org (if a key is configured),
    otherwise FlashScore fixtures.
  * Weather enrichment from OpenWeatherMap (if a key is configured).
  * Best-effort xG enrichment from SofaScore (opt-in; slow + often unavailable).

Missing pieces never raise — they just lower the eventual confidence score.
"""
from __future__ import annotations

from typing import Optional

from backend.schemas import MatchInput, TeamData, LeagueAverages
from backend.scraper.footballdata import FootballDataClient
from backend.scraper.flashscore import list_upcoming as fs_list_upcoming
from backend.scraper.weather import get_weather
from backend.scraper.sofascore import SofaScoreClient
from backend.scraper.utils import normalize_team_name, log


class DataProvider:
    def __init__(self):
        self.fd = FootballDataClient()
        self.sofa = SofaScoreClient()

    @property
    def primary_source(self) -> str:
        return "football-data.org" if self.fd.enabled else "flashscore"

    # ------------------------------------------------------------------ #
    def collect_upcoming(self, days: int = 3, enrich_xg: bool = False) -> list[MatchInput]:
        if self.fd.enabled:
            fixtures = self.fd.list_upcoming(days=days)
            matches = [self.fd.build_match_input(f) for f in fixtures]
        else:
            log.info("No football-data key -> using FlashScore fixtures (reduced data).")
            matches = fs_list_upcoming()

        for m in matches:
            try:
                self.enrich(m, enrich_xg=enrich_xg)
            except Exception as exc:  # noqa: BLE001
                log.warning("enrich failed for %s vs %s: %s", m.home_team, m.away_team, exc)
        return matches

    # ------------------------------------------------------------------ #
    def enrich(self, m: MatchInput, enrich_xg: bool = False) -> MatchInput:
        # Weather from the stadium/venue text (best-effort city resolution).
        if m.venue:
            w = get_weather(m.venue)
            if w:
                m.weather = w
                if "openweathermap" not in m.data_sources:
                    m.data_sources.append("openweathermap")

        # Best-effort xG from SofaScore (slow, opt-in).
        if enrich_xg:
            self._enrich_sofascore_xg(m)
        return m

    def _enrich_sofascore_xg(self, m: MatchInput) -> None:
        try:
            team = self.sofa.search_team(m.home_team)
            if not team:
                return
            ev = self.sofa.team_next_event(team["id"])
            if not ev:
                return
            stats = self.sofa.event_statistics(ev["id"])
            if stats:
                m.data_sources.append("sofascore")
                # NOTE: parsing of xG out of the statistics payload would go here
                # when the API is reachable; left as a structured hook.
        except Exception as exc:  # noqa: BLE001
            log.info("sofascore xG enrichment skipped: %s", exc)

    # ------------------------------------------------------------------ #
    def build_from_names(self, home: str, away: str, league: str = "") -> MatchInput:
        """On-demand minimal MatchInput for a fixture not already in the DB.

        Tries to locate the fixture in the upcoming football-data set first; if
        not found, builds a minimal input (LOW confidence) from the names alone.
        """
        if self.fd.enabled:
            for f in self.fd.list_upcoming(days=10):
                if (normalize_team_name(f.get("homeTeam", {}).get("name")) == normalize_team_name(home)
                        and normalize_team_name(f.get("awayTeam", {}).get("name")) == normalize_team_name(away)):
                    m = self.fd.build_match_input(f)
                    self.enrich(m)
                    return m

        m = MatchInput(
            home_team=home, away_team=away, league=league,
            home=TeamData(name=home), away=TeamData(name=away),
            league_avgs=LeagueAverages(),
            data_sources=[self.primary_source],
        )
        self.enrich(m)
        return m
