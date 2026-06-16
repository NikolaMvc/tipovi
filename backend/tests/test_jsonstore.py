"""Tests for the static JSON storage / tip-generation layer."""
from __future__ import annotations

import backend.jsonstore as js


def _resp(home, away, hw, dr, aw, over, btts_yes, mid=None, date="2026-06-16"):
    return {
        "match": {"id": mid, "home_team": home, "away_team": away, "league": "PL",
                  "date": f"{date}T19:00:00+00:00", "event_id": mid},
        "prediction": {"home_win_prob": hw, "draw_prob": dr, "away_win_prob": aw},
        "markets": {"over_under_2_5": {"over": over, "under": round(100 - over, 2)},
                    "btts": {"yes": btts_yes, "no": round(100 - btts_yes, 2)}},
        "value_bets": [{"market": "1X2", "pick": "Home Win", "odds": 1.5}],
    }


def test_generate_top_tips_ranks_by_probability():
    responses = [
        _resp("A", "B", 70, 20, 10, 55, 60, mid="1"),   # safest = Home Win 70
        _resp("C", "D", 30, 30, 40, 80, 50, mid="2"),   # safest = Over 80
        _resp("E", "F", 33, 34, 33, 51, 52, mid="3"),   # safest = Draw 34
    ]
    tips = js.generate_top_tips(responses, n=2)
    assert len(tips) == 2
    assert tips[0]["probability"] == 80 and tips[0]["pick"] == "Over 2.5"
    assert tips[1]["probability"] == 70 and tips[1]["pick"] == "Home Win"
    # odds picked up from value_bets where available
    assert tips[1]["odds"] == 1.5


def test_tip_outcome_all_markets():
    assert js.tip_outcome("Home Win", "1X2", 2, 1) == "WON"
    assert js.tip_outcome("Away Win", "1X2", 2, 1) == "LOST"
    assert js.tip_outcome("Draw", "1X2", 1, 1) == "WON"
    assert js.tip_outcome("Over 2.5", "O/U 2.5", 2, 1) == "WON"
    assert js.tip_outcome("Under 2.5", "O/U 2.5", 1, 1) == "WON"
    assert js.tip_outcome("Yes", "BTTS", 1, 1) == "WON"
    assert js.tip_outcome("No", "BTTS", 2, 0) == "WON"


def test_settle_tips():
    tips = [
        {"match_id": "1", "market": "1X2", "pick": "Home Win", "status": "PENDING"},
        {"match_id": "2", "market": "O/U 2.5", "pick": "Over 2.5", "status": "PENDING"},
    ]
    results = {"1": {"home_goals": 2, "away_goals": 0}, "2": {"home_goals": 0, "away_goals": 0}}
    n = js.settle_tips(tips, results)
    assert n == 2
    assert tips[0]["status"] == "WON"
    assert tips[1]["status"] == "LOST"
    assert tips[0]["final_score"] == "2-0"


def test_save_cleanup_and_index(tmp_path, monkeypatch):
    # redirect storage dirs to a temp location
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "PRED_DIR", tmp_path / "predictions")
    monkeypatch.setattr(js, "RES_DIR", tmp_path / "results")
    monkeypatch.setattr(js, "TIPS_DIR", tmp_path / "tips")
    monkeypatch.setattr(js, "INDEX_FILE", tmp_path / "index.json")

    js.save_predictions("2026-06-16", [_resp("A", "B", 70, 20, 10, 55, 60, mid="1")])
    js.save_predictions("2020-01-01", [_resp("Old", "Match", 50, 30, 20, 50, 50, mid="9")])
    removed = js.cleanup_old(rolling_days=3)
    assert removed == 1  # the 2020 file is gone
    assert (tmp_path / "predictions" / "2026-06-16.json").exists()
    idx = js.write_index()
    assert "2026-06-16" in idx["prediction_days"]
    assert "2020-01-01" not in idx["prediction_days"]
