"""FlashScore scraper (no public API -> stealth-browser DOM scraping).

Two jobs:
  * ``all_matches(day_offset)`` — independently discover EVERY scheduled match for a
    day across ALL leagues FlashScore shows (the main /football/ page, grouped by
    ``.headerLeague``). This is what fills leagues football-data.org doesn't cover.
  * ``list_upcoming`` / ``team_form`` — the older per-league helpers, kept as fallback.

Parsing is best-effort and resilient: anything it cannot read is simply omitted so
the pipeline degrades gracefully.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.schemas import MatchInput, TeamData, FormEntry, LeagueAverages
from backend.scraper.utils import fetch_browser, normalize_team_name, log

WWW = "https://www.flashscore.com"
FOOTBALL = f"{WWW}/football/"
# Internal data feed (fast HTTP, no browser) — gives both teams' recent form + H2H.
FEED = f"{WWW}/x/feed/"
FSIGN = "SW9D1eZo"

# League landing pages used by the per-league fallback helper.
DEFAULT_LEAGUES = {
    "Premier League": "/football/england/premier-league/fixtures/",
    "LaLiga": "/football/spain/laliga/fixtures/",
    "Serie A": "/football/italy/serie-a/fixtures/",
    "Bundesliga": "/football/germany/bundesliga/fixtures/",
    "Ligue 1": "/football/france/ligue-1/fixtures/",
}

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _text(node) -> str:
    try:
        return node.get_all_text(strip=True)
    except Exception:
        return ""


def _first(node, sel: str):
    try:
        els = node.css(sel)
        return els[0] if els else None
    except Exception:
        return None


def _has_class(node, name: str) -> bool:
    try:
        cls = node.attrib.get("class", "")
    except Exception:
        cls = ""
    return name in cls.split()


def _extract_grouped(resp) -> list[dict]:
    """Walk the page in document order, tracking the current league header so each
    match row is tagged with its league + country. Returns ALL rows (any status)."""
    out: list[dict] = []
    if not resp:
        return out
    try:
        nodes = resp.css(".headerLeague, .event__match")
    except Exception:
        return out

    cur_league = ""
    cur_country = ""
    for node in nodes:
        if _has_class(node, "headerLeague"):
            cat = _first(node, ".headerLeague__category-text")
            title = _first(node, ".headerLeague__title-text")
            cur_country = _text(cat)
            cur_league = _text(title)
            continue
        # event__match row
        try:
            home = _first(node, ".event__participant--home") or _first(node, ".event__homeParticipant")
            away = _first(node, ".event__participant--away") or _first(node, ".event__awayParticipant")
            home_name, away_name = _text(home), _text(away)
            if not home_name or not away_name:
                continue
            hs = _first(node, ".event__score--home")
            as_ = _first(node, ".event__score--away")
            row_id = (node.attrib.get("id") or "")  # e.g. "g_1_n9TEVLhA"
            eid = row_id.split("g_1_", 1)[-1] if "g_1_" in row_id else ""
            out.append({
                "home": home_name,
                "away": away_name,
                "time": _text(_first(node, ".event__time")),
                "home_score": _text(hs),
                "away_score": _text(as_),
                "league": cur_league,
                "country": cur_country,
                "event_id": eid,
            })
        except Exception:
            continue
    return out


def _is_scheduled(row: dict) -> bool:
    """Not started yet. FlashScore shows a dash placeholder ("-") in the score
    cells of upcoming matches, so a match counts as *played* only when a score
    cell actually contains a digit; upcoming matches still carry a HH:MM kickoff."""
    hs = (row.get("home_score") or "").strip()
    as_ = (row.get("away_score") or "").strip()
    if any(c.isdigit() for c in hs) or any(c.isdigit() for c in as_):
        return False
    t = (row.get("time") or "").strip()
    # kickoff label like "19:45" (today) or "18.06. 20:00" (future day)
    return bool(re.search(r"\d{1,2}:\d{2}", t))


def all_matches(day_offset: int = 0) -> list[MatchInput]:
    """Every scheduled match for (today + day_offset) across ALL leagues."""
    target_date = (datetime.now(timezone.utc).date() + timedelta(days=day_offset))

    def nav(page):
        # Advance the date bar `day_offset` days using the forward arrow.
        for _ in range(day_offset):
            try:
                page.locator('[data-testid="wcl-icon-action-navigation-arrow-right"]').first.click(timeout=8000)
                page.wait_for_timeout(1800)
            except Exception:
                break
        try:
            page.wait_for_selector(".event__match", timeout=15000)
        except Exception:
            pass
        return page

    resp = fetch_browser(
        FOOTBALL, network_idle=True, wait=2500, timeout=60000,
        wait_selector=".event__match" if day_offset == 0 else None,
        page_action=nav if day_offset > 0 else None,
    )
    rows = _extract_grouped(resp)
    scheduled = [r for r in rows if _is_scheduled(r)]
    log.info("flashscore all-leagues day+%d: %d rows, %d scheduled across leagues",
             day_offset, len(rows), len(scheduled))

    matches: list[MatchInput] = []
    for r in scheduled:
        league = f"{r['country']}: {r['league']}".strip(": ") if r.get("country") else r.get("league", "")
        # build a naive datetime on the target day from the HH:MM label
        md = None
        mt = re.search(r"(\d{1,2}):(\d{2})$", r.get("time", ""))
        if mt:
            md = datetime(target_date.year, target_date.month, target_date.day,
                          int(mt.group(1)), int(mt.group(2)), tzinfo=timezone.utc)
        matches.append(MatchInput(
            home_team=r["home"], away_team=r["away"], league=league or "Other",
            match_date=md, venue="", event_id=r.get("event_id") or None,
            home=TeamData(name=r["home"], team_id=r.get("event_id") or None),
            away=TeamData(name=r["away"]),
            league_avgs=LeagueAverages(),
            data_sources=["flashscore"],
        ))
    return matches


# --------------------------------------------------------------------------- #
# Per-match enrichment via the internal H2H feed (form for both teams + H2H)
# --------------------------------------------------------------------------- #
def _feed_text(name: str) -> Optional[str]:
    from scrapling.fetchers import Fetcher
    try:
        r = Fetcher.get(f"{FEED}{name}", headers={"x-fsign": FSIGN, "Referer": f"{WWW}/"},
                        impersonate="chrome", timeout=15)
        if r.status == 200 and r.body:
            return r.body.decode("utf-8", "replace") if isinstance(r.body, bytes) else str(r.body)
    except Exception as exc:  # noqa: BLE001
        log.info("flashscore feed %s failed: %s", name, exc)
    return None


def fetch_form_h2h(event_id: str, home_name: str = "", away_name: str = ""):
    """Return (home_entries, away_entries, H2HData, home_last_date, away_last_date)
    parsed from the df_hh feed (Overall tab only). Empty/None on failure."""
    from backend.schemas import H2HData
    raw = _feed_text(f"df_hh_1_{event_id}")
    if not raw:
        return [], [], H2HData(), None, None

    tab = None
    form_sections: list[list[dict]] = []   # ordered: [home_form, away_form, ...]
    h2h_records: list[dict] = []
    cur_section = None      # "form" | "h2h" | None
    rec = None

    def push():
        if rec and rec.get("KU") not in (None, ""):
            if cur_section == "form" and form_sections:
                form_sections[-1].append(dict(rec))
            elif cur_section == "h2h":
                h2h_records.append(dict(rec))

    for f in raw.split("¬"):
        if "÷" not in f:
            continue
        k, v = f.split("÷", 1)
        if k == "~KA":
            tab = v
        elif k == "~KB":
            push(); rec = None
            if tab != "Overall":
                cur_section = None
                continue
            if v.startswith("Last matches:"):
                cur_section = "form"; form_sections.append([])
            elif "Head-to-head" in v:
                cur_section = "h2h"
            else:
                cur_section = None
        elif k == "~KC":
            push(); rec = {"ts": v} if cur_section else None
        elif rec is not None and k in ("KJ", "KK", "KU", "KT", "KS", "WIS"):
            rec[k] = v.lstrip("*")
    push()

    def to_entries(records):
        from backend.schemas import FormEntry
        entries, last = [], None
        for m in records:
            try:
                ku, kt = int(m["KU"]), int(m["KT"])
            except (ValueError, KeyError):
                continue
            is_home = m.get("KS") == "home"
            gf, ga = (ku, kt) if is_home else (kt, ku)
            opp = m.get("KK") if is_home else m.get("KJ")
            entries.append(FormEntry(opponent=opp or "", is_home=is_home,
                                     goals_for=gf, goals_against=ga, date=m.get("ts")))
            try:
                ts = int(m["ts"])
                if last is None or ts > last:
                    last = ts
            except (ValueError, KeyError):
                pass
        from datetime import datetime, timezone
        last_dt = datetime.fromtimestamp(last, timezone.utc) if last else None
        return entries, last_dt

    home_entries, home_last = to_entries(form_sections[0]) if len(form_sections) > 0 else ([], None)
    away_entries, away_last = to_entries(form_sections[1]) if len(form_sections) > 1 else ([], None)

    # H2H aggregates relative to the CURRENT fixture's home team (by name match).
    from backend.scraper.utils import normalize_team_name
    nh, na = normalize_team_name(home_name), normalize_team_name(away_name)
    goals = []
    hw = dw = aw = 0
    for m in h2h_records:
        try:
            ku, kt = int(m["KU"]), int(m["KT"])
        except (ValueError, KeyError):
            continue
        goals.append(ku + kt)
        hist_home = normalize_team_name(m.get("KJ", ""))
        # goals for the current home team in this historical meeting
        if nh and hist_home == nh:
            gf, ga = ku, kt
        elif na and hist_home == na:
            gf, ga = kt, ku
        else:
            # fall back to raw orientation if names don't line up
            gf, ga = ku, kt
        if gf > ga:
            hw += 1
        elif gf < ga:
            aw += 1
        else:
            dw += 1
    h2h = H2HData(home_wins=hw, draws=dw, away_wins=aw,
                  matches=len(goals), avg_goals=round(sum(goals) / len(goals), 2) if goals else None)
    return home_entries, away_entries, h2h, home_last, away_last


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
            home = _first(row, ".event__participant--home") or _first(row, ".event__homeParticipant")
            away = _first(row, ".event__participant--away") or _first(row, ".event__awayParticipant")
            time_node = _first(row, ".event__time")
            home_name = _text(home)
            away_name = _text(away)
            if not home_name or not away_name:
                continue
            # scores (present for finished matches)
            hs = _first(row, ".event__score--home")
            as_ = _first(row, ".event__score--away")
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
