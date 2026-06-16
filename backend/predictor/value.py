"""Value-bet detection and Kelly staking."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ValueBet:
    market: str
    pick: str
    our_prob: float        # percent
    implied_prob: float    # percent
    value: float           # percentage points (our - implied)
    kelly_pct: float       # full Kelly fraction of bankroll, percent
    half_kelly_pct: float
    rating: str
    odds: float

    def as_dict(self) -> dict:
        return {
            "market": self.market,
            "pick": self.pick,
            "our_prob": round(self.our_prob, 2),
            "implied_prob": round(self.implied_prob, 2),
            "value": round(self.value, 2),
            "kelly_pct": round(self.kelly_pct, 2),
            "half_kelly_pct": round(self.half_kelly_pct, 2),
            "rating": self.rating,
            "odds": self.odds,
        }


def _rating(value_pct: float) -> str:
    if value_pct > 10:
        return "STRONG_VALUE"
    if value_pct >= 5:
        return "GOOD_VALUE"
    if value_pct >= 0:
        return "SLIGHT_VALUE"
    return "NO_VALUE"


def evaluate(market: str, pick: str, our_prob_pct: float, odds: Optional[float]) -> Optional[ValueBet]:
    """Return a ValueBet, or None if no odds available."""
    if not odds or odds <= 1.0:
        return None
    p = our_prob_pct / 100.0
    implied = 1.0 / odds
    value_pp = (p - implied) * 100.0

    # Kelly fraction: (p*odd - 1) / (odd - 1)
    kelly = (p * odds - 1.0) / (odds - 1.0)
    kelly_pct = max(0.0, kelly) * 100.0

    return ValueBet(
        market=market,
        pick=pick,
        our_prob=our_prob_pct,
        implied_prob=implied * 100.0,
        value=value_pp,
        kelly_pct=kelly_pct,
        half_kelly_pct=kelly_pct / 2.0,
        rating=_rating(value_pp),
        odds=odds,
    )


def find_value_bets(markets_probs: dict, odds) -> list[dict]:
    """Evaluate the standard markets and return only positive-value bets.

    markets_probs: {
        "home_win": %, "draw": %, "away_win": %,
        "over_2_5": %, "under_2_5": %, "btts_yes": %, "btts_no": %,
    }
    odds: OddsData (or None)
    """
    if odds is None:
        return []

    candidates = [
        ("1X2", "Home Win", markets_probs.get("home_win"), odds.home),
        ("1X2", "Draw", markets_probs.get("draw"), odds.draw),
        ("1X2", "Away Win", markets_probs.get("away_win"), odds.away),
        ("O/U 2.5", "Over 2.5", markets_probs.get("over_2_5"), odds.over_2_5),
        ("O/U 2.5", "Under 2.5", markets_probs.get("under_2_5"), odds.under_2_5),
        ("BTTS", "Yes", markets_probs.get("btts_yes"), odds.btts_yes),
        ("BTTS", "No", markets_probs.get("btts_no"), odds.btts_no),
    ]

    out: list[dict] = []
    for market, pick, prob, odd in candidates:
        if prob is None or odd is None:
            continue
        vb = evaluate(market, pick, prob, odd)
        if vb and vb.value > 0:
            out.append(vb.as_dict())
    out.sort(key=lambda x: x["value"], reverse=True)
    return out
