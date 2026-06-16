"""Persistence helpers shared by the worker and the API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.models import Match, Prediction, MyTip, Result
from backend.schemas import MatchInput


# --------------------------------------------------------------------------- #
# Matches + predictions
# --------------------------------------------------------------------------- #
def upsert_match(db: Session, m: MatchInput) -> Match:
    q = select(Match).where(
        Match.home_team == m.home_team,
        Match.away_team == m.away_team,
        Match.match_date == m.match_date,
    )
    match = db.execute(q).scalar_one_or_none()
    if match is None:
        match = Match(
            home_team=m.home_team, away_team=m.away_team, league=m.league,
            match_date=m.match_date, venue=m.venue, event_id=m.event_id,
            status="UPCOMING",
        )
        db.add(match)
    else:
        match.league = m.league or match.league
        match.venue = m.venue or match.venue
        match.event_id = m.event_id or match.event_id
    match.scraped_at = datetime.now(timezone.utc)
    db.flush()
    return match


def save_prediction(db: Session, match: Match, response: dict) -> Prediction:
    pred = match.prediction
    if pred is None:
        pred = Prediction()
        match.prediction = pred  # links match_id and populates the in-session relationship
    p = response["prediction"]
    pred.home_win = p["home_win_prob"]
    pred.draw = p["draw_prob"]
    pred.away_win = p["away_win_prob"]
    pred.predicted_outcome = p["predicted_outcome"]
    pred.confidence = p["confidence"]
    pred.confidence_score = p["confidence_score"]
    pred.missing_data = p["missing_data"]
    pred.lambda_home = p["lambda"]["home"]
    pred.lambda_away = p["lambda"]["away"]
    pred.predicted_goals = p["predicted_goals"]
    pred.most_likely_scores = p["most_likely_scores"]
    pred.markets = response["markets"]
    pred.value_bets = response["value_bets"]
    pred.poisson_matrix = response["poisson_matrix"]
    pred.breakdown = response["breakdown"]
    pred.response_json = response
    pred.computed_at = datetime.now(timezone.utc)
    db.add(pred)
    db.flush()
    return pred


def store_match_prediction(db: Session, m: MatchInput, response: dict) -> Match:
    match = upsert_match(db, m)
    # keep the DB ids / status in the stored payload
    response["match"]["id"] = match.id
    response["match"]["status"] = match.status
    save_prediction(db, match, response)
    db.commit()
    return match


def get_upcoming(db: Session, limit: int = 100) -> list[Match]:
    q = (
        select(Match)
        .where(Match.status == "UPCOMING")
        .order_by(Match.match_date.asc().nulls_last() if hasattr(Match.match_date, "asc") else Match.match_date)
        .limit(limit)
    )
    return list(db.execute(q).scalars().all())


def get_match(db: Session, match_id: int) -> Optional[Match]:
    return db.get(Match, match_id)


def find_match_by_teams(db: Session, home: str, away: str) -> Optional[Match]:
    from backend.scraper.utils import normalize_team_name
    nh, na = normalize_team_name(home), normalize_team_name(away)
    for match in db.execute(select(Match)).scalars().all():
        if (normalize_team_name(match.home_team) == nh
                and normalize_team_name(match.away_team) == na):
            return match
    return None


def search_teams(db: Session, q: str, limit: int = 10) -> list[str]:
    from backend.scraper.utils import normalize_team_name
    nq = normalize_team_name(q)
    names: set[str] = set()
    for match in db.execute(select(Match)).scalars().all():
        for name in (match.home_team, match.away_team):
            if nq in normalize_team_name(name):
                names.add(name)
    return sorted(names)[:limit]


# --------------------------------------------------------------------------- #
# Tips
# --------------------------------------------------------------------------- #
def add_tip(db: Session, match_id: int, market: str, pick: str, odds: float,
            our_prob: float, value: float, kelly_pct: float) -> MyTip:
    tip = MyTip(match_id=match_id, market=market, pick=pick, odds=odds,
                our_prob=our_prob, value=value, kelly_pct=kelly_pct, status="PENDING")
    db.add(tip)
    db.commit()
    db.refresh(tip)
    return tip


def get_tips(db: Session) -> list[MyTip]:
    return list(db.execute(select(MyTip).order_by(MyTip.created_at.desc())).scalars().all())


def delete_tip(db: Session, tip_id: int) -> bool:
    tip = db.get(MyTip, tip_id)
    if not tip:
        return False
    db.delete(tip)
    db.commit()
    return True


# --------------------------------------------------------------------------- #
# Results + settlement
# --------------------------------------------------------------------------- #
def record_result(db: Session, match: Match, home_goals: int, away_goals: int) -> Result:
    res = match.result
    if res is None:
        res = Result()
        match.result = res
    res.final_home_goals = home_goals
    res.final_away_goals = away_goals
    res.settled_at = datetime.now(timezone.utc)
    db.add(res)
    match.status = "FINISHED"
    db.flush()
    settle_tips_for_match(db, match, home_goals, away_goals)
    db.commit()
    return res


def _tip_outcome(pick: str, market: str, hg: int, ag: int) -> str:
    total = hg + ag
    pick_l = pick.lower()
    if market == "1X2":
        if "home" in pick_l:
            return "WON" if hg > ag else "LOST"
        if "away" in pick_l:
            return "WON" if ag > hg else "LOST"
        if "draw" in pick_l:
            return "WON" if hg == ag else "LOST"
    if market in ("O/U 2.5", "OU", "Over/Under"):
        if "over" in pick_l:
            return "WON" if total >= 3 else "LOST"
        if "under" in pick_l:
            return "WON" if total < 3 else "LOST"
    if market == "BTTS":
        both = hg >= 1 and ag >= 1
        if "yes" in pick_l:
            return "WON" if both else "LOST"
        if "no" in pick_l:
            return "WON" if not both else "LOST"
    return "PENDING"


def settle_tips_for_match(db: Session, match: Match, hg: int, ag: int) -> None:
    for tip in match.tips:
        if tip.status != "PENDING":
            continue
        outcome = _tip_outcome(tip.pick, tip.market, hg, ag)
        if outcome in ("WON", "LOST"):
            tip.status = outcome
            tip.settled_at = datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Statistics (assumes a flat 1-unit stake per tip)
# --------------------------------------------------------------------------- #
def get_stats(db: Session) -> dict:
    tips = get_tips(db)
    total = len(tips)
    won = [t for t in tips if t.status == "WON"]
    lost = [t for t in tips if t.status == "LOST"]
    pending = [t for t in tips if t.status == "PENDING"]
    settled = len(won) + len(lost)

    profit = sum((t.odds - 1.0) for t in won) - len(lost)
    win_rate = (len(won) / settled * 100) if settled else 0.0
    roi = (profit / settled * 100) if settled else 0.0

    # Breakdown by market
    markets: dict[str, dict] = {}
    for t in tips:
        mk = markets.setdefault(t.market, {"total": 0, "won": 0, "lost": 0, "profit": 0.0})
        mk["total"] += 1
        if t.status == "WON":
            mk["won"] += 1
            mk["profit"] += t.odds - 1.0
        elif t.status == "LOST":
            mk["lost"] += 1
            mk["profit"] -= 1.0
    for mk in markets.values():
        s = mk["won"] + mk["lost"]
        mk["win_rate"] = round(mk["won"] / s * 100, 1) if s else 0.0
        mk["profit"] = round(mk["profit"], 2)

    # Cumulative profit over time (settled tips, chronological)
    timeline = []
    cum = 0.0
    for t in sorted([t for t in tips if t.settled_at], key=lambda x: x.settled_at):
        cum += (t.odds - 1.0) if t.status == "WON" else (-1.0 if t.status == "LOST" else 0.0)
        timeline.append({"date": t.settled_at.isoformat(), "profit": round(cum, 2)})

    return {
        "total_tips": total,
        "won": len(won),
        "lost": len(lost),
        "pending": len(pending),
        "settled": settled,
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 1),
        "profit": round(profit, 2),
        "by_market": markets,
        "timeline": timeline,
    }
