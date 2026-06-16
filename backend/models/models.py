"""ORM models for matches, predictions, tips and results."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Integer, String, Float, DateTime, ForeignKey, JSON, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("home_team", "away_team", "match_date", name="uq_match"),
        Index("ix_match_status_date", "status", "match_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_team: Mapped[str] = mapped_column(String(120), index=True)
    away_team: Mapped[str] = mapped_column(String(120), index=True)
    league: Mapped[str] = mapped_column(String(120), default="")
    match_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    venue: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="UPCOMING")  # UPCOMING/LIVE/FINISHED
    event_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    prediction: Mapped["Prediction"] = relationship(
        back_populates="match", uselist=False, cascade="all, delete-orphan")
    result: Mapped["Result"] = relationship(
        back_populates="match", uselist=False, cascade="all, delete-orphan")
    tips: Mapped[list["MyTip"]] = relationship(
        back_populates="match", cascade="all, delete-orphan")


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), unique=True)

    home_win: Mapped[float] = mapped_column(Float, default=0.0)
    draw: Mapped[float] = mapped_column(Float, default=0.0)
    away_win: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_outcome: Mapped[str] = mapped_column(String(20), default="")
    confidence: Mapped[str] = mapped_column(String(10), default="LOW")
    confidence_score: Mapped[int] = mapped_column(Integer, default=0)
    missing_data: Mapped[list] = mapped_column(JSON, default=list)
    lambda_home: Mapped[float] = mapped_column(Float, default=0.0)
    lambda_away: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_goals: Mapped[dict] = mapped_column(JSON, default=dict)
    most_likely_scores: Mapped[list] = mapped_column(JSON, default=list)
    markets: Mapped[dict] = mapped_column(JSON, default=dict)
    value_bets: Mapped[list] = mapped_column(JSON, default=list)
    poisson_matrix: Mapped[list] = mapped_column(JSON, default=list)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    # Full serialized response payload for instant API serving.
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    match: Mapped["Match"] = relationship(back_populates="prediction")


class MyTip(Base):
    __tablename__ = "my_tips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    market: Mapped[str] = mapped_column(String(40))
    pick: Mapped[str] = mapped_column(String(60))
    odds: Mapped[float] = mapped_column(Float, default=0.0)
    our_prob: Mapped[float] = mapped_column(Float, default=0.0)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    kelly_pct: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING/WON/LOST
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    match: Mapped["Match"] = relationship(back_populates="tips")


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), unique=True)
    final_home_goals: Mapped[int] = mapped_column(Integer, default=0)
    final_away_goals: Mapped[int] = mapped_column(Integer, default=0)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    match: Mapped["Match"] = relationship(back_populates="result")
