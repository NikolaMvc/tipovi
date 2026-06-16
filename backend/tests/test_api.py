"""End-to-end API tests over a seeded SQLite DB."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import store
from backend.predictor.engine import predict
import backend.tests.test_footballdata as fd


client = TestClient(app)


def _seed(db_session):
    c = fd._client_with_mocks()
    m = c.build_match_input(fd.FIXTURE)
    resp = predict(m)
    match = store.store_match_prediction(db_session, m, resp)
    return match, resp


def test_health(db_session):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_matches_and_detail(db_session):
    match, _ = _seed(db_session)
    r = client.get("/api/matches?status=upcoming")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    mid = match.id
    d = client.get(f"/api/match/{mid}").json()
    assert len(d["poisson_matrix"]) == 7
    assert d["match"]["home_team"] == "Manchester City"


def test_tip_lifecycle_and_stats(db_session):
    match, resp = _seed(db_session)
    tip = client.post("/api/tips", json={
        "match_id": match.id, "market": "1X2", "pick": "Home Win",
        "odds": 1.8, "our_prob": resp["prediction"]["home_win_prob"],
        "value": 5.0, "kelly_pct": 4.0,
    }).json()
    assert "id" in tip
    tips = client.get("/api/tips").json()
    assert len(tips["active"]) >= 1

    # settle the match -> tip should resolve and feed stats
    store.record_result(db_session, match, 2, 1)
    stats = client.get("/api/stats").json()
    assert stats["won"] >= 1
    assert stats["win_rate"] > 0

    assert client.delete(f"/api/tips/{tip['id']}").json()["deleted"] == tip["id"]


def test_match_404(db_session):
    assert client.get("/api/match/999999").status_code == 404
