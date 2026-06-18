"""Validation of the table-position-aware form scoring (spec example)."""
from __future__ import annotations

import pytest

from backend.schemas import FormEntry
from backend.predictor.lambda_calc import compute_form_score, form_match_points


def _entry(is_home, gf, ga, pos):
    return FormEntry(is_home=is_home, goals_for=gf, goals_against=ga, opponent_position=pos)


def test_spec_example_home_020_away_040():
    # Home: L home vs24->0, D away vs22->0, L home vs4->0, L away vs1->1, L away vs15->0 => 1/5 = 0.20
    home = [
        _entry(True, 0, 1, 24),
        _entry(False, 1, 1, 22),
        _entry(True, 0, 2, 4),
        _entry(False, 0, 1, 1),
        _entry(False, 0, 3, 15),
    ]
    # Away: D home vs23->0, L away vs2->1, L home vs17->0, D away vs10->1, L home vs6->0 => 2/5 = 0.40
    away = [
        _entry(True, 1, 1, 23),
        _entry(False, 0, 1, 2),
        _entry(True, 0, 2, 17),
        _entry(False, 2, 2, 10),
        _entry(True, 0, 1, 6),
    ]
    home_score, _, _ = compute_form_score(home)
    away_score, _, _ = compute_form_score(away)
    assert home_score == pytest.approx(0.20)
    assert away_score == pytest.approx(0.40)
    assert away_score > home_score  # away slight favourite by form


def test_form_points_table():
    # Wins
    assert form_match_points("W", True, 3) == 3   # home vs top-5
    assert form_match_points("W", True, 6) == 2   # home vs 6+
    assert form_match_points("W", False, 8) == 3  # away vs 1-8
    assert form_match_points("W", False, 9) == 2  # away vs 9+
    # Draws
    assert form_match_points("D", True, 8) == 1
    assert form_match_points("D", True, 9) == 0
    assert form_match_points("D", False, 2) == 2
    assert form_match_points("D", False, 14) == 1
    assert form_match_points("D", False, 15) == 0
    # Losses
    assert form_match_points("L", True, 2) == 1
    assert form_match_points("L", True, 3) == 0
    assert form_match_points("L", False, 8) == 1
    assert form_match_points("L", False, 9) == 0


def test_unknown_position_uses_mid_table():
    # pos None -> mid-table (10); away loss vs mid-table (>8) -> 0
    assert form_match_points("L", False, None) == 0
    s, details, est = compute_form_score([_entry(False, 0, 1, None)])
    assert est == 1 and details[0]["position_estimated"] is True
