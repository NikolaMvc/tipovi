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
    def _canon(name: str) -> str:
        """Punctuation- and word-order-insensitive form so that naming variants
        across sources collapse (e.g. 'Congo DR' == 'D.R. Congo')."""
        import re as _re
        n = normalize_team_name(name)
        n = n.replace(".", "").replace("'", "").replace("’", "")  # keep "D.R." as "dr"
        tokens = [t for t in _re.split(r"[^a-z0-9]+", n) if t]
        return " ".join(sorted(tokens))

    def _key(self, m: MatchInput) -> tuple:
        d = m.match_date.date().isoformat() if m.match_date else ""
        return (self._canon(m.home_team), self._canon(m.away_team), d)

    def collect_upcoming(self, days: int = 3, enrich_xg: bool = False,
                         require_odds: bool = True) -> list[MatchInput]:
        """ALL matches for the window: football-data.org for the 12 covered leagues
        (rich data) PLUS FlashScore's independent all-leagues discovery for every
        other competition. Deduplicated; football-data wins on overlap.

        With ``require_odds`` (default), matches without a betting market on any
        source are dropped from the whole pipeline."""
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

        # 3) Enrich form/H2H/odds (NOT xG yet); never raises.
        for m in matches:
            try:
                self.enrich(m, enrich_xg=enrich_xg)
            except Exception as exc:  # noqa: BLE001
                log.warning("enrich failed for %s vs %s: %s", m.home_team, m.away_team, exc)

        # 4) ODDS FILTER — keep only matches with a betting market on some source.
        if require_odds:
            before = len(matches)
            matches = [m for m in matches if m.odds is not None]
            log.info("odds filter: %d -> %d matches (dropped %d without odds)",
                     before, len(matches), before - len(matches))

        # 5) xG enrichment only on the matches we keep (expensive: per-match stats).
        for m in matches:
            if "flashscore" in m.data_sources and "football-data.org" not in m.data_sources:
                try:
                    self._enrich_xg(m)
                except Exception as exc:  # noqa: BLE001
                    log.info("xg enrich skipped for %s: %s", m.home_team, exc)
        return matches

    # ------------------------------------------------------------------ #
    @staticmethod
    def _season_from_recent(entries):
        from backend.schemas import TeamSeasonStats
        s = TeamSeasonStats(matches_played=len(entries))
        if not entries:
            return s
        home = [e for e in entries if e.is_home]
        away = [e for e in entries if not e.is_home]

        def avg(lst, attr):
            return round(sum(getattr(e, attr) for e in lst) / len(lst), 3) if lst else None

        ov_sc = avg(entries, "goals_for")
        ov_co = avg(entries, "goals_against")
        s.avg_scored_home = avg(home, "goals_for") if home else ov_sc
        s.avg_scored_away = avg(away, "goals_for") if away else ov_sc
        s.avg_conceded_home = avg(home, "goals_against") if home else ov_co
        s.avg_conceded_away = avg(away, "goals_against") if away else ov_co
        return s

    def _enrich_flashscore(self, m: MatchInput) -> None:
        """Populate form + H2H + odds for a FlashScore-only match via its internal
        feeds (xG is added later, only for matches that survive the odds filter)."""
        from backend.scraper.flashscore import fetch_form_h2h, fetch_odds

        odds = fetch_odds(m.event_id)
        if odds:
            m.odds = odds
            if "flashscore-odds" not in m.data_sources:
                m.data_sources.append("flashscore-odds")

        h_recent, a_recent, h2h, h_last, a_last = fetch_form_h2h(
            m.event_id, m.home_team, m.away_team)
        if h_recent:
            m.home.recent = h_recent
            m.home.season = self._season_from_recent(h_recent)
            m.home.last_match_date = h_last
        if a_recent:
            m.away.recent = a_recent
            m.away.season = self._season_from_recent(a_recent)
            m.away.last_match_date = a_last
        if h2h and h2h.matches:
            m.h2h = h2h
        if (h_recent or a_recent) and "flashscore-feed" not in m.data_sources:
            m.data_sources.append("flashscore-feed")

    def _enrich_xg(self, m: MatchInput) -> None:
        """Real FlashScore xG -> shot-based proxy -> goals (marked by source)."""
        from backend.scraper.flashscore import team_xg_from_recent
        if m.home.recent:
            xg, xga, src = team_xg_from_recent(m.home.recent)
            if xg is not None:
                m.home.season.avg_xg, m.home.season.avg_xga = xg, xga
                m.home.xg_source = src
        if m.away.recent:
            xg, xga, src = team_xg_from_recent(m.away.recent)
            if xg is not None:
                m.away.season.avg_xg, m.away.season.avg_xga = xg, xga
                m.away.xg_source = src
        if (m.home.xg_source or m.away.xg_source) and "flashscore-stats" not in m.data_sources:
            m.data_sources.append("flashscore-stats")

    def enrich(self, m: MatchInput, enrich_xg: bool = False) -> MatchInput:
        # FlashScore-only matches: pull form + H2H from the data feed.
        if m.event_id and "flashscore" in m.data_sources and "football-data.org" not in m.data_sources:
            try:
                self._enrich_flashscore(m)
            except Exception as exc:  # noqa: BLE001
                log.info("flashscore feed enrich skipped for %s: %s", m.home_team, exc)

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
