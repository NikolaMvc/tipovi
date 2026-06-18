"""Normalized data contract shared between the scraper layer and the predictor.

Every field is optional with a sensible default so that the predictor can apply
*graceful degradation*: a missing field simply disables the related factor and
lowers the confidence score instead of crashing the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TeamSeasonStats:
    """Aggregated season numbers for one team, split by venue where possible."""
    matches_played: int = 0
    # Goals scored / conceded per game, split home/away
    avg_scored_home: Optional[float] = None
    avg_scored_away: Optional[float] = None
    avg_conceded_home: Optional[float] = None
    avg_conceded_away: Optional[float] = None
    # Expected goals (best-effort, often missing)
    avg_xg: Optional[float] = None
    avg_xga: Optional[float] = None
    clean_sheets: int = 0
    # Standings
    position: Optional[int] = None
    points: Optional[int] = None


@dataclass
class FormEntry:
    date: Optional[str] = None
    opponent: str = ""
    is_home: bool = True
    goals_for: int = 0
    goals_against: int = 0
    match_id: Optional[str] = None  # source match id (for fetching shot/xG stats)
    competition: str = ""          # competition of this historical match (league/cup/friendly)
    is_league: bool = True         # True for league matches (used for form gathering)
    opponent_position: Optional[int] = None   # opponent's CURRENT table position
    position_estimated: bool = False          # True when we fell back to mid-table

    @property
    def result(self) -> str:
        if self.goals_for > self.goals_against:
            return "W"
        if self.goals_for < self.goals_against:
            return "L"
        return "D"


@dataclass
class TeamData:
    name: str = ""
    team_id: Optional[str] = None
    season: TeamSeasonStats = field(default_factory=TeamSeasonStats)
    # Most-recent-first list of matches (used for form + xG correction + fatigue)
    recent: list[FormEntry] = field(default_factory=list)
    missing_players: list[dict] = field(default_factory=list)  # {name, reason, key}
    lineup_known: bool = False  # True once lineups/injuries were actually scraped
    last_match_date: Optional[datetime] = None
    # xG provenance: None | "real" (FlashScore xG) | "proxy" (from shots) | "goals"
    xg_source: Optional[str] = None

    def last_n_results(self, n: int = 5) -> list[str]:
        return [e.result for e in self.recent[:n]]

    def avg_goals_scored_recent(self, n: int = 5) -> Optional[float]:
        sub = self.recent[:n]
        if not sub:
            return None
        return sum(e.goals_for for e in sub) / len(sub)

    def avg_xg_recent(self, n: int = 5) -> Optional[float]:
        return self.season.avg_xg


@dataclass
class H2HData:
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    avg_goals: Optional[float] = None
    matches: int = 0


@dataclass
class RefereeData:
    name: str = ""
    avg_cards: Optional[float] = None
    avg_penalties: Optional[float] = None


@dataclass
class WeatherData:
    temp: Optional[float] = None
    conditions: Optional[str] = None
    wind_speed: Optional[float] = None
    gol_suppressing: bool = False


@dataclass
class OddsData:
    # decimal odds
    home: Optional[float] = None
    draw: Optional[float] = None
    away: Optional[float] = None
    over_2_5: Optional[float] = None
    under_2_5: Optional[float] = None
    btts_yes: Optional[float] = None
    btts_no: Optional[float] = None


@dataclass
class LeagueAverages:
    """League baselines; defaults are typical top-division European values."""
    avg_home_goals: float = 1.50
    avg_away_goals: float = 1.15
    avg_scored_home: float = 1.50
    avg_scored_away: float = 1.15
    avg_conceded_home: float = 1.15
    avg_conceded_away: float = 1.50
    is_default: bool = True  # True when we fell back to generic constants


@dataclass
class MatchInput:
    """Everything the predictor needs for a single fixture."""
    home_team: str = ""
    away_team: str = ""
    league: str = ""
    match_date: Optional[datetime] = None
    venue: str = ""
    event_id: Optional[str] = None

    home: TeamData = field(default_factory=TeamData)
    away: TeamData = field(default_factory=TeamData)
    league_avgs: LeagueAverages = field(default_factory=LeagueAverages)
    h2h: H2HData = field(default_factory=H2HData)
    referee: Optional[RefereeData] = None
    weather: Optional[WeatherData] = None
    odds: Optional[OddsData] = None

    data_sources: list[str] = field(default_factory=list)

    def rest_days(self, team: TeamData) -> Optional[int]:
        if not self.match_date or not team.last_match_date:
            return None
        return max(0, (self.match_date.date() - team.last_match_date.date()).days)
