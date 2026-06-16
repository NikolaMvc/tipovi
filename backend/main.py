"""FastAPI application — reads finished predictions from the DB for instant
responses. The only heavy path is POST /api/predict (on-demand for a fixture not
yet in the DB), which computes once and then persists it."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import get_db, init_db
from backend import store, cache
from backend.scraper.provider import DataProvider
from backend.scraper.footballdata import FootballDataClient
from backend.predictor.engine import predict
from backend.scraper.utils import get_logger

log = get_logger("api")

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    global _scheduler
    # Optionally run the scheduler in-process (single-dyno deployments).
    if os.getenv("RUN_WORKER_IN_API", "false").lower() == "true":
        from backend.worker.scheduler import start_background_scheduler
        _scheduler = start_background_scheduler()
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="PredictAI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #
def _match_summary(match) -> dict:
    pred = match.prediction
    return {
        "match": {
            "id": match.id,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "league": match.league,
            "date": match.match_date.isoformat() if match.match_date else None,
            "venue": match.venue,
            "status": match.status,
        },
        "prediction": None if not pred else {
            "home_win_prob": pred.home_win,
            "draw_prob": pred.draw,
            "away_win_prob": pred.away_win,
            "predicted_outcome": pred.predicted_outcome,
            "confidence": pred.confidence,
            "confidence_score": pred.confidence_score,
            "missing_data": pred.missing_data,
        },
    }


def _match_detail(match) -> dict:
    if match.prediction and match.prediction.response_json:
        payload = dict(match.prediction.response_json)
        payload["match"]["id"] = match.id
        payload["match"]["status"] = match.status
        return payload
    return _match_summary(match)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class PredictRequest(BaseModel):
    home_team: str
    away_team: str
    league: str = ""


class TipRequest(BaseModel):
    match_id: int
    market: str
    pick: str
    odds: float
    our_prob: float = 0.0
    value: float = 0.0
    kelly_pct: float = 0.0


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/matches")
def list_matches(status: str = Query("upcoming"), db: Session = Depends(get_db)):
    key = f"matches:{status}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    matches = store.get_upcoming(db) if status.lower() == "upcoming" else []
    data = {"matches": [_match_summary(m) for m in matches], "count": len(matches)}
    cache.set(key, data)
    return data


@app.get("/api/match/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)):
    key = f"match:{match_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    match = store.get_match(db, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    data = _match_detail(match)
    cache.set(key, data)
    return data


@app.post("/api/predict")
def predict_on_demand(req: PredictRequest, db: Session = Depends(get_db)):
    # Already in DB? Return instantly.
    existing = store.find_match_by_teams(db, req.home_team, req.away_team)
    if existing and existing.prediction:
        return _match_detail(existing)

    provider = DataProvider()
    m = provider.build_from_names(req.home_team, req.away_team, req.league)
    response = predict(m)
    match = store.store_match_prediction(db, m, response)
    cache.invalidate("matches:upcoming")
    return _match_detail(match)


@app.get("/api/search/team")
def search_team(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return {"results": store.search_teams(db, q)}


@app.post("/api/tips")
def add_tip(req: TipRequest, db: Session = Depends(get_db)):
    match = store.get_match(db, req.match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    tip = store.add_tip(db, req.match_id, req.market, req.pick, req.odds,
                        req.our_prob, req.value, req.kelly_pct)
    cache.invalidate("stats")
    return {"id": tip.id, "status": tip.status}


@app.get("/api/tips")
def list_tips(db: Session = Depends(get_db)):
    tips = store.get_tips(db)
    out = []
    for t in tips:
        out.append({
            "id": t.id,
            "match_id": t.match_id,
            "home_team": t.match.home_team if t.match else "",
            "away_team": t.match.away_team if t.match else "",
            "league": t.match.league if t.match else "",
            "market": t.market,
            "pick": t.pick,
            "odds": t.odds,
            "our_prob": t.our_prob,
            "value": t.value,
            "kelly_pct": t.kelly_pct,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "settled_at": t.settled_at.isoformat() if t.settled_at else None,
        })
    active = [t for t in out if t["status"] == "PENDING"]
    settled = [t for t in out if t["status"] != "PENDING"]
    return {"active": active, "settled": settled, "all": out}


@app.delete("/api/tips/{tip_id}")
def delete_tip(tip_id: int, db: Session = Depends(get_db)):
    if not store.delete_tip(db, tip_id):
        raise HTTPException(404, "Tip not found")
    cache.invalidate("stats")
    return {"deleted": tip_id}


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    cached = cache.get("stats")
    if cached is not None:
        return cached
    data = store.get_stats(db)
    cache.set("stats", data, ttl=300)
    return data


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    fd = FootballDataClient()
    upcoming = len(store.get_upcoming(db))
    return {
        "status": "ok",
        "upcoming_matches": upcoming,
        "sources": {
            "football_data_org": "configured" if fd.enabled else "no_key",
            "openweathermap": "configured" if settings.OPENWEATHER_API_KEY else "no_key",
            "flashscore": "available",
            "sofascore_api": "blocked (403 challenge) — best-effort fallback only",
        },
        "redis": "connected" if cache._redis() else "disabled",
    }


@app.get("/")
def root():
    return {"name": "PredictAI API", "docs": "/docs", "health": "/api/health"}
