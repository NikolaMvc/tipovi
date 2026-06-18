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
    cur_url = ""
    for node in nodes:
        if _has_class(node, "headerLeague"):
            cat = _first(node, ".headerLeague__category-text")
            title = _first(node, ".headerLeague__title-text")
            link = _first(node, "a")
            cur_country = _text(cat)
            cur_league = _text(title)
            cur_url = (link.attrib.get("href") if link is not None else "") or ""
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
                "league_url": cur_url,
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


_NATIONAL_AREAS = {"WORLD", "EUROPE", "AFRICA", "SOUTH AMERICA",
                   "NORTH & CENTRAL AMERICA", "ASIA", "OCEANIA"}


def all_matches(day_offset: int = 0) -> list[MatchInput]:
    """Every scheduled match for (today + day_offset) across ALL leagues, read from
    FlashScore's full-day fixtures feed (f_1_<day>_2_en_1). Fast HTTP, complete —
    the rendered page only shows a partial subset, the feed has the whole schedule."""
    raw = _feed_text(f"f_1_{day_offset}_2_en_1")
    if not raw:
        log.warning("flashscore matches feed empty for day+%d", day_offset)
        return []

    matches: list[MatchInput] = []
    cur_league = cur_country = cur_url = ""
    rec: dict | None = None
    total = scheduled = 0

    def flush(r):
        nonlocal scheduled
        if not r:
            return
        if r.get("AC") != "1":          # AC==1 => scheduled / not started
            return
        home, away = r.get("AE", ""), r.get("AF", "")
        if not home or not away:
            return
        scheduled += 1
        country, league_name, url = r["country"], r["league"], r["url"]
        league = league_name or country  # ~ZA already formatted as "COUNTRY: League"
        is_national = country.upper() in _NATIONAL_AREAS
        is_friendly = "friendly" in league_name.lower()
        md = None
        try:
            md = datetime.fromtimestamp(int(r["AD"]), timezone.utc)
        except (ValueError, KeyError, TypeError):
            pass
        eid = r.get("AA") or None
        matches.append(MatchInput(
            home_team=home, away_team=away, league=league or "Other",
            match_date=md, venue="", event_id=eid,
            league_url=url, is_national=is_national, is_friendly=is_friendly,
            home=TeamData(name=home, team_id=eid), away=TeamData(name=away),
            league_avgs=LeagueAverages(), data_sources=["flashscore"],
        ))

    for f in raw.split("¬"):
        if "÷" not in f:
            continue
        k, v = f.split("÷", 1)
        if k == "~ZA":
            flush(rec); rec = None
            cur_league = v
        elif k == "ZY":
            cur_country = v
        elif k == "ZL":
            cur_url = v
        elif k == "~AA":
            flush(rec); total += 1
            rec = {"AA": v, "league": cur_league, "country": cur_country, "url": cur_url}
        elif rec is not None and k in ("AC", "AD", "AE", "AF"):
            rec[k] = v
    flush(rec)

    log.info("flashscore feed day+%d: %d total, %d scheduled across leagues",
             day_offset, total, scheduled)
    return matches


# --------------------------------------------------------------------------- #
# League standings (current table positions) — rendered DOM, cached per league
# --------------------------------------------------------------------------- #
_STANDINGS_CACHE: dict[str, dict] = {}


_TID_RE = re.compile(r'tournamentId"?\s*[:=]\s*"([A-Za-z0-9]+)"')
_SID_RE = re.compile(r'tournamentStageId"?\s*[:=]\s*"([A-Za-z0-9]+)"')


def fetch_standings(league_url: str) -> dict:
    """Return {normalized_team_name: position} for a league. Cached. Empty when the
    competition has no table (knockout / friendlies).

    Fast path (no browser): GET the standings page HTML to read the tournament +
    stage ids, then read the ``to_<tid>_<sid>_1`` feed (rank=~TR, name=TN)."""
    if not league_url:
        return {}
    if league_url in _STANDINGS_CACHE:
        return _STANDINGS_CACHE[league_url]

    from scrapling.fetchers import Fetcher
    table: dict = {}
    url = f"{WWW}{league_url.rstrip('/')}/standings/"
    try:
        r = Fetcher.get(url, impersonate="chrome", timeout=18)
        html = r.body.decode("utf-8", "replace") if isinstance(r.body, bytes) else str(r.body)
    except Exception:  # noqa: BLE001
        html = ""
    tid = _TID_RE.search(html)
    sid = _SID_RE.search(html)
    if tid and sid:
        raw = _feed_text(f"to_{tid.group(1)}_{sid.group(1)}_1")
        if raw:
            cur_rank = None
            for f in raw.split("¬"):
                if "÷" not in f:
                    continue
                k, v = f.split("÷", 1)
                if k == "~TR":
                    try:
                        cur_rank = int(v)
                    except ValueError:
                        cur_rank = None
                elif k == "TN" and cur_rank is not None:
                    nm = normalize_team_name(v)
                    if nm:
                        table[nm] = cur_rank
                    cur_rank = None
    log.info("standings %s -> %d teams", league_url, len(table))
    _STANDINGS_CACHE[league_url] = table
    return table


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
        elif rec is not None and k in ("KP", "KF", "KJ", "KK", "KU", "KT", "KS", "WIS"):
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
                                     goals_for=gf, goals_against=ga, date=m.get("ts"),
                                     match_id=m.get("KP"), competition=m.get("KF", "")))
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


# --------------------------------------------------------------------------- #
# Match statistics feed  ->  real xG / shot-based proxy xG
# --------------------------------------------------------------------------- #
_STATS_CACHE: dict[str, dict] = {}


def fetch_match_stats(match_id: str) -> dict:
    """Parse the df_st feed for one match -> {xg_home, xg_away, shots_*, sot_*,
    corners_*}. Values are None when the match has no such stat. Cached."""
    if not match_id:
        return {}
    if match_id in _STATS_CACHE:
        return _STATS_CACHE[match_id]
    raw = _feed_text(f"df_st_1_{match_id}")
    out: dict = {}
    if raw:
        name = None
        for f in raw.split("¬"):
            if f.startswith("SG÷"):
                name = f[3:]
            elif f.startswith("SH÷") and name:
                out[(name, "h")] = f[3:]
            elif f.startswith("SI÷") and name:
                out[(name, "a")] = f[3:]

        def num(label, side, integer=False):
            v = out.get((label, side))
            if v is None:
                return None
            v = v.replace("%", "").split("(")[0].strip()
            try:
                return int(v) if integer else float(v)
            except ValueError:
                return None

        result = {
            "xg_home": num("Expected goals (xG)", "h"),
            "xg_away": num("Expected goals (xG)", "a"),
            "shots_home": num("Total shots", "h", True),
            "shots_away": num("Total shots", "a", True),
            "sot_home": num("Shots on target", "h", True),
            "sot_away": num("Shots on target", "a", True),
            "corners_home": num("Corner kicks", "h", True),
            "corners_away": num("Corner kicks", "a", True),
        }
    else:
        result = {}
    _STATS_CACHE[match_id] = result
    return result


def _proxy_xg(shots, sot, corners) -> Optional[float]:
    """Shot-based xG proxy, calibrated so a typical match (~4 SoT) ~ 1.3 xG."""
    if sot is None and shots is None:
        return None
    sot = sot or 0
    shots = shots or 0
    corners = corners or 0
    off_target = max(0, shots - sot)
    return round(max(0.0, 0.34 * sot + 0.03 * off_target + 0.025 * corners), 3)


def team_xg_from_recent(entries, limit: int = 3):
    """Average a team's xG-for / xG-against over its recent matches.

    Per match: use FlashScore real xG when present, else a shot-based proxy, else
    fall back to the goals scored/conceded. Returns (avg_xg, avg_xga, source) where
    source is 'real' | 'proxy' | 'goals' | None."""
    xf_list, xa_list = [], []
    n_real = n_proxy = n_goals = 0
    for e in entries[:limit]:
        st = fetch_match_stats(e.match_id) if e.match_id else {}
        if st.get("xg_home") is not None and st.get("xg_away") is not None:
            xf, xa = (st["xg_home"], st["xg_away"]) if e.is_home else (st["xg_away"], st["xg_home"])
            n_real += 1
        elif st.get("shots_home") is not None or st.get("sot_home") is not None:
            ph = _proxy_xg(st.get("shots_home"), st.get("sot_home"), st.get("corners_home"))
            pa = _proxy_xg(st.get("shots_away"), st.get("sot_away"), st.get("corners_away"))
            xf, xa = (ph, pa) if e.is_home else (pa, ph)
            n_proxy += 1
        else:
            xf, xa = float(e.goals_for), float(e.goals_against)
            n_goals += 1
        if xf is not None and xa is not None:
            xf_list.append(xf); xa_list.append(xa)
    if not xf_list:
        return None, None, None
    avg = lambda L: round(sum(L) / len(L), 3)
    if n_real >= max(n_proxy, n_goals) and n_real > 0:
        source = "real"
    elif n_proxy > 0:
        source = "proxy"
    else:
        source = "goals"
    return avg(xf_list), avg(xa_list), source


# --------------------------------------------------------------------------- #
# Odds feed  ->  drop matches with no market
# --------------------------------------------------------------------------- #
# FlashScore pre-match odds are served by a GraphQL endpoint (clean JSON, fast HTTP,
# no browser, no x-fsign). The same FlashScore event id is the GraphQL eventId.
ODDS_API = "https://global.ds.lsapp.eu/odds/pq_graphql"
ODDS_HASH = "ope2"
# Try a few common bookmakers; use the first that quotes the match. Kept short so
# matches without odds don't cost many requests.
ODDS_BOOKMAKERS = [16, 417, 5, 2]


def _odds_query(event_id: str, bet_type: str, bookmaker: int):
    import json
    from scrapling.fetchers import Fetcher
    try:
        r = Fetcher.get(ODDS_API, params={
            "_hash": ODDS_HASH, "eventId": event_id, "bookmakerId": bookmaker,
            "betType": bet_type, "betScope": "FULL_TIME",
        }, impersonate="chrome", timeout=12)
        if r.status != 200:
            return None
        body = r.body.decode("utf-8", "replace") if isinstance(r.body, bytes) else str(r.body)
        return (json.loads(body).get("data") or {}).get("findPrematchOddsForBookmaker")
    except Exception:  # noqa: BLE001
        return None


def _fval(item):
    try:
        return float(item["value"]) if item and item.get("value") else None
    except (ValueError, TypeError, KeyError):
        return None


def fetch_odds(event_id: str):
    """Pre-match 1X2 / O-U 2.5 / BTTS odds via FlashScore's GraphQL odds API.
    Returns an OddsData or None when no bookmaker quotes the match."""
    from backend.schemas import OddsData
    if not event_id:
        return None
    odds = OddsData()

    # 1X2 — find the first bookmaker that quotes this match.
    bk_used = None
    for bk in ODDS_BOOKMAKERS:
        d = _odds_query(event_id, "HOME_DRAW_AWAY", bk)
        if d and _fval(d.get("home")):
            odds.home = _fval(d.get("home"))
            odds.draw = _fval(d.get("draw"))
            odds.away = _fval(d.get("away"))
            bk_used = bk
            break
    if bk_used is None:
        return None

    # Over/Under — pick the 2.5 line.
    ou = _odds_query(event_id, "OVER_UNDER", bk_used)
    if ou:
        for opp in ou.get("opportunities", []):
            if (opp.get("handicap") or {}).get("value") in ("2.5", "2.50"):
                odds.over_2_5 = _fval(opp.get("over"))
                odds.under_2_5 = _fval(opp.get("under"))
                break

    # Both teams to score.
    bt = _odds_query(event_id, "BOTH_TEAMS_TO_SCORE", bk_used)
    if bt:
        odds.btts_yes = _fval(bt.get("yes"))
        odds.btts_no = _fval(bt.get("no"))

    return odds if odds.home else None


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
