"""Static JSON storage layer.

Everything the static frontend reads lives under frontend/public/data/:

    predictions/<YYYY-MM-DD>.json   full prediction payloads for that day
    results/<YYYY-MM-DD>.json       finished match scores (for settling tips)
    tips/<YYYY-MM-DD>.json          auto-generated top-N tips for that day
    index.json                      meta: available days + last run timestamp

A rolling window keeps only the last ROLLING_DAYS of each, so the folder stays
small and always current.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import settings, DATA_DIR

PRED_DIR = DATA_DIR / "predictions"
RES_DIR = DATA_DIR / "results"
TIPS_DIR = DATA_DIR / "tips"
INDEX_FILE = DATA_DIR / "index.json"

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


# --------------------------------------------------------------------------- #
# Low-level IO
# --------------------------------------------------------------------------- #
def _ensure_dirs() -> None:
    for d in (DATA_DIR, PRED_DIR, RES_DIR, TIPS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _write(path: Path, payload: dict) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def match_id(response: dict) -> str:
    """Stable id for a match: football-data event id when present, else a slug."""
    m = response.get("match", {})
    if m.get("event_id"):
        return str(m["event_id"])
    date = (m.get("date") or "")[:10]
    home = re.sub(r"\W+", "-", (m.get("home_team") or "").lower()).strip("-")
    away = re.sub(r"\W+", "-", (m.get("away_team") or "").lower()).strip("-")
    return f"{date}-{home}-vs-{away}"


# --------------------------------------------------------------------------- #
# Save
# --------------------------------------------------------------------------- #
def save_predictions(date_str: str, responses: list[dict]) -> None:
    for r in responses:
        r["match"]["id"] = match_id(r)
    _write(PRED_DIR / f"{date_str}.json", {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(responses),
        "matches": responses,
    })


def save_results(date_str: str, results: list[dict]) -> None:
    _write(RES_DIR / f"{date_str}.json", {"date": date_str, "results": results})


def save_tips(date_str: str, tips: list[dict]) -> None:
    _write(TIPS_DIR / f"{date_str}.json", {"date": date_str, "tips": tips})


# --------------------------------------------------------------------------- #
# Tip generation (auto top-N by highest single-market probability)
# --------------------------------------------------------------------------- #
def _candidate_picks(resp: dict) -> list[dict]:
    # Tips are 1X2 only — the single highest-probability outcome (1 / X / 2).
    # O/U and BTTS are still shown in the match detail, just not picked as tips.
    p = resp.get("prediction", {})
    cands = [
        ("1X2", "Home Win", p.get("home_win_prob")),
        ("1X2", "Draw", p.get("draw_prob")),
        ("1X2", "Away Win", p.get("away_win_prob")),
    ]
    return [{"market": m, "pick": pk, "probability": pr} for m, pk, pr in cands if pr is not None]


def _odds_for(resp: dict, market: str, pick: str) -> Optional[float]:
    # Prefer the raw odds for the 1X2 pick (so favourites, which aren't value bets,
    # still show a price); fall back to the value-bet odds.
    o = resp.get("odds") or {}
    by_pick = {"Home Win": o.get("home"), "Draw": o.get("draw"), "Away Win": o.get("away")}
    if by_pick.get(pick) is not None:
        return by_pick[pick]
    for vb in resp.get("value_bets", []):
        if vb.get("market") == market and vb.get("pick") == pick:
            return vb.get("odds")
    return None


def generate_top_tips(responses: list[dict], n: Optional[int] = None) -> list[dict]:
    """For each match pick its single safest market, then take the top-N across the
    day ranked by probability (descending)."""
    n = n or settings.TIP_COUNT
    best_per_match = []
    for resp in responses:
        cands = _candidate_picks(resp)
        if not cands:
            continue
        best = max(cands, key=lambda c: c["probability"])
        m = resp.get("match", {})
        best_per_match.append({
            "match_id": m.get("id") or match_id(resp),
            "home_team": m.get("home_team"),
            "away_team": m.get("away_team"),
            "league": m.get("league"),
            "date": m.get("date"),
            "market": best["market"],
            "pick": best["pick"],
            "probability": best["probability"],
            "odds": _odds_for(resp, best["market"], best["pick"]),
            "status": "PENDING",
        })
    best_per_match.sort(key=lambda t: t["probability"], reverse=True)
    return best_per_match[:n]


# --------------------------------------------------------------------------- #
# Settlement
# --------------------------------------------------------------------------- #
def tip_outcome(pick: str, market: str, hg: int, ag: int) -> str:
    total = hg + ag
    pl = pick.lower()
    if market == "1X2":
        if "home" in pl:
            return "WON" if hg > ag else "LOST"
        if "away" in pl:
            return "WON" if ag > hg else "LOST"
        if "draw" in pl:
            return "WON" if hg == ag else "LOST"
    if market.startswith("O/U"):
        if "over" in pl:
            return "WON" if total >= 3 else "LOST"
        if "under" in pl:
            return "WON" if total < 3 else "LOST"
    if market == "BTTS":
        both = hg >= 1 and ag >= 1
        if "yes" in pl:
            return "WON" if both else "LOST"
        if "no" in pl:
            return "WON" if not both else "LOST"
    return "PENDING"


def settle_tips(tips: list[dict], results_by_id: dict) -> int:
    """Colour each tip from the matching result. Returns how many were settled."""
    settled = 0
    for tip in tips:
        if tip.get("status") in ("WON", "LOST"):
            continue
        res = results_by_id.get(str(tip.get("match_id")))
        if not res:
            continue
        outcome = tip_outcome(tip["pick"], tip["market"], res["home_goals"], res["away_goals"])
        if outcome in ("WON", "LOST"):
            tip["status"] = outcome
            tip["final_score"] = f"{res['home_goals']}-{res['away_goals']}"
            settled += 1
    return settled


def all_results_by_id() -> dict:
    """Merge every stored results day into {match_id: result}."""
    out: dict = {}
    if not RES_DIR.exists():
        return out
    for f in RES_DIR.glob("*.json"):
        data = _read(f) or {}
        for r in data.get("results", []):
            out[str(r.get("id"))] = r
    return out


# --------------------------------------------------------------------------- #
# Index + rolling cleanup
# --------------------------------------------------------------------------- #
def _dates_in(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    dates = []
    for f in folder.glob("*.json"):
        m = _DATE_RE.match(f.name)
        if m:
            dates.append(m.group(1))
    return sorted(dates)


def cleanup_old(rolling_days: Optional[int] = None) -> int:
    """Delete prediction/result/tip files older than the rolling window."""
    rolling_days = rolling_days or settings.ROLLING_DAYS
    cutoff = (datetime.now(timezone.utc).date()).toordinal() - rolling_days
    removed = 0
    for folder in (PRED_DIR, RES_DIR, TIPS_DIR):
        for f in folder.glob("*.json"):
            m = _DATE_RE.match(f.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            if d.toordinal() < cutoff:
                f.unlink()
                removed += 1
    return removed


def write_index() -> dict:
    payload = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "prediction_days": _dates_in(PRED_DIR),
        "result_days": _dates_in(RES_DIR),
        "tip_days": _dates_in(TIPS_DIR),
    }
    _write(INDEX_FILE, payload)
    return payload
