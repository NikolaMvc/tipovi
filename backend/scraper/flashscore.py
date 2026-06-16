"""FlashScore scraper (no public API -> stealth-browser DOM scraping).

FlashScore renders match rows as ``.event__match`` elements. This module extracts
upcoming fixtures and recent team form from the rendered HTML. Parsing is
best-effort and resilient: anything it cannot read is simply omitted so the
pipeline degrades gracefully.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Optional

from backend.schemas import MatchInput, TeamData, FormEntry, LeagueAverages
from backend.scraper.utils import fetch_browser, normalize_team_name, log

WWW = "https://www.flashscore.com"

# League landing pages used to discover fixtures when no API key is configured.
DEFAULT_LEAGUES = {
    "Premier League": "/football/england/premier-league/fixtures/",
    "LaLiga": "/football/spain/laliga/fixtures/",
    "Serie A": "/football/italy/serie-a/fixtures/",
    "Bundesliga": "/football/germany/bundesliga/fixtures/",
    "Ligue 1": "/football/france/ligue-1/fixtures/",
}


def _text(node) -> str:
    try:
        return node.get_all_text(strip=True)
    except Exception:
        return ""


def _extract_matches(resp) -> list[dict]:
    """Pull (home, away, time) tuples from rendered FlashScore HTML."""
    out: list[dict] = []
    if not resp:
        return out
    try:
        rows = resp.css(".event__match")
    except Exception:
        rows = []
    for row in rows:
        try:
            home = row.css_first(".event__participant--home") or row.css_first(".event__homeParticipant")
            away = row.css_first(".event__participant--away") or row.css_first(".event__awayParticipant")
            time_node = row.css_first(".event__time")
            home_name = _text(home)
            away_name = _text(away)
            if not home_name or not away_name:
                continue
            # scores (present for finished matches)
            hs = row.css_first(".event__score--home")
            as_ = row.css_first(".event__score--away")
            out.append({
                "home": home_name,
                "away": away_name,
                "time": _text(time_node),
                "home_score": _text(hs),
                "away_score": _text(as_),
            })
        except Exception:
            continue
    return out


def list_upcoming(leagues: Optional[dict] = None) -> list[MatchInput]:
    """Discover upcoming fixtures across the configured league pages."""
    leagues = leagues or DEFAULT_LEAGUES
    matches: list[MatchInput] = []
    for league_name, path in leagues.items():
        resp = fetch_browser(f"{WWW}{path}", network_idle=True, wait=2000, wait_selector=".event__match", timeout=25000)
        rows = _extract_matches(resp)
        log.info("flashscore: %d rows for %s", len(rows), league_name)
        for row in rows:
            if row.get("home_score"):  # already played
                continue
            matches.append(MatchInput(
                home_team=row["home"],
                away_team=row["away"],
                league=league_name,
                venue="",
                home=TeamData(name=row["home"]),
                away=TeamData(name=row["away"]),
                league_avgs=LeagueAverages(),  # generic baselines
                data_sources=["flashscore"],
            ))
    return matches


def team_form(team_results_url: str, team_name: str, limit: int = 10) -> list[FormEntry]:
    """Best-effort recent form from a team's results page."""
    resp = fetch_browser(f"{WWW}{team_results_url}", network_idle=True, wait=2000, wait_selector=".event__match", timeout=25000)
    rows = _extract_matches(resp)
    entries: list[FormEntry] = []
    for row in rows[:limit]:
        try:
            hs, as_ = int(row.get("home_score") or 0), int(row.get("away_score") or 0)
        except ValueError:
            continue
        is_home = normalize_team_name(row["home"]) == normalize_team_name(team_name)
        gf, ga = (hs, as_) if is_home else (as_, hs)
        opp = row["away"] if is_home else row["home"]
        entries.append(FormEntry(opponent=opp, is_home=is_home, goals_for=gf, goals_against=ga))
    return entries


def _main():
    parser = argparse.ArgumentParser(description="FlashScore scraper debug tool")
    parser.add_argument("--league", default="Premier League")
    args = parser.parse_args()
    path = DEFAULT_LEAGUES.get(args.league, DEFAULT_LEAGUES["Premier League"])
    resp = fetch_browser(f"{WWW}{path}", network_idle=True, wait=2000, wait_selector=".event__match", timeout=25000)
    rows = _extract_matches(resp)
    print(f"== FlashScore {args.league}: {len(rows)} rows ==")
    for r in rows[:15]:
        print(f"  {r['home']}  vs  {r['away']}   [{r['time']}] {r['home_score']}-{r['away_score']}")


if __name__ == "__main__":
    _main()
