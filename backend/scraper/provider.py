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
from backend.scraper.flashscore import all_matches as fs_all_matches
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
    @staticmethod
    def _key(m: MatchInput) -> tuple:
        d = m.match_date.date().isoformat() if m.match_date else ""
        return (normalize_team_name(m.home_team), normalize_team_name(m.away_team), d)

    def collect_upcoming(self, days: int = 3, enrich_xg: bool = False) -> list[MatchInput]:
        """ALL matches for the window: football-data.org for the 12 covered leagues
        (rich data) PLUS FlashScore's independent all-leagues discovery for every
        other competition. Deduplicated; football-data wins on overlap."""
        matches: list[MatchInput] = []
        seen: set[tuple] = set()

        # 1) football-data.org — rich data for the covered leagues.
        if self.fd.enabled:
            for f in self.fd.list_upcoming(days=days):
                m = self.fd.build_match_input(f)
                k = self._key(m)
                if k not in seen:
                    seen.add(k)
                    matches.append(m)
            log.info("football-data contributed %d matches", len(matches))

        # 2) FlashScore — independently discover EVERY other league for each day.
        fd_count = len(matches)
        for offset in range(days):
            try:
                for m in fs_all_matches(offset):
                    k = self._key(m)
                    if k in seen:
                        continue  # already covered (richer) by football-data
                    seen.add(k)
                    matches.append(m)
            except Exception as exc:  # noqa: BLE001
                log.warning("flashscore all_matches(day+%d) failed: %s", offset, exc)
        log.info("flashscore added %d extra matches across all leagues", len(matches) - fd_count)

        # 3) Enrich everything (weather + best-effort xG); never raises.
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
