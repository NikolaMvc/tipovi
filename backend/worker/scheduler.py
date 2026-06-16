"""Background worker (APScheduler).

Jobs (all heavy work happens here, never in the request path):
  * every SCRAPE_INTERVAL_HOURS  : scrape upcoming fixtures, predict, store
  * every REFRESH_INTERVAL_HOURS : refresh fixtures kicking off in < 6h (late news)
  * every SETTLE_INTERVAL_HOURS  : fetch finished results, settle tips

On startup it runs the first scrape immediately so the DB is never empty.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from backend.config import settings
from backend.models import SessionLocal, init_db
from backend.models.models import Match
from backend import store
from backend.scraper.provider import DataProvider
from backend.scraper.footballdata import FootballDataClient
from backend.predictor.engine import predict
from backend.scraper.utils import get_logger

log = get_logger("worker")


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def scrape_and_predict(days: int | None = None, enrich_xg: bool = False) -> int:
    """Scrape upcoming fixtures, run predictions and persist them. Returns count."""
    days = days or settings.LOOKAHEAD_DAYS
    log.info("JOB scrape_and_predict (days=%s) starting", days)
    provider = DataProvider()
    matches = provider.collect_upcoming(days=days, enrich_xg=enrich_xg)
    db = SessionLocal()
    n = 0
    try:
        for m in matches:
            try:
                response = predict(m)
                store.store_match_prediction(db, m, response)
                n += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("predict/store failed for %s vs %s: %s",
                            m.home_team, m.away_team, exc)
        log.info("JOB scrape_and_predict stored %d predictions", n)
    finally:
        db.close()
    return n


def refresh_soon() -> int:
    """Re-predict matches that kick off within the next 6 hours (late injuries)."""
    log.info("JOB refresh_soon starting")
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=6)
    db = SessionLocal()
    provider = DataProvider()
    n = 0
    try:
        upcoming = [
            mt for mt in store.get_upcoming(db)
            if mt.match_date and now <= mt.match_date <= soon
        ]
        for mt in upcoming:
            try:
                m = provider.build_from_names(mt.home_team, mt.away_team, mt.league)
                response = predict(m)
                store.store_match_prediction(db, m, response)
                n += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("refresh failed for match %s: %s", mt.id, exc)
        log.info("JOB refresh_soon refreshed %d matches", n)
    finally:
        db.close()
    return n


def settle_finished() -> int:
    """Find matches whose kickoff has passed, fetch the score, settle tips."""
    log.info("JOB settle_finished starting")
    fd = FootballDataClient()
    if not fd.enabled:
        log.info("settle_finished: no football-data key; skipping result fetch")
        return 0
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    n = 0
    try:
        candidates = [
            mt for mt in db.query(Match).filter(Match.status != "FINISHED").all()
            if mt.match_date and mt.match_date < now - timedelta(hours=2) and mt.event_id
        ]
        for mt in candidates:
            try:
                data = fd.match(int(mt.event_id))
                if not data or data.get("status") != "FINISHED":
                    continue
                ft = data.get("score", {}).get("fullTime", {})
                hg, ag = ft.get("home"), ft.get("away")
                if hg is None or ag is None:
                    continue
                store.record_result(db, mt, hg, ag)
                n += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("settle failed for match %s: %s", mt.id, exc)
        log.info("JOB settle_finished settled %d matches", n)
    finally:
        db.close()
    return n


# --------------------------------------------------------------------------- #
# Scheduler wiring
# --------------------------------------------------------------------------- #
def _register(scheduler) -> None:
    scheduler.add_job(scrape_and_predict, "interval", hours=settings.SCRAPE_INTERVAL_HOURS,
                      id="scrape_and_predict", max_instances=1, coalesce=True)
    scheduler.add_job(refresh_soon, "interval", hours=settings.REFRESH_INTERVAL_HOURS,
                      id="refresh_soon", max_instances=1, coalesce=True)
    scheduler.add_job(settle_finished, "interval", hours=settings.SETTLE_INTERVAL_HOURS,
                      id="settle_finished", max_instances=1, coalesce=True)


def start_background_scheduler() -> BackgroundScheduler:
    """Used when the worker runs in-process with the API."""
    init_db()
    scheduler = BackgroundScheduler(timezone="UTC")
    _register(scheduler)
    scheduler.start()
    if settings.RUN_SCRAPE_ON_STARTUP:
        scheduler.add_job(scrape_and_predict, id="startup_scrape", max_instances=1)
    log.info("Background scheduler started")
    return scheduler


def run_worker() -> None:
    """Standalone worker process entrypoint (Railway 'worker' service)."""
    init_db()
    scheduler = BlockingScheduler(timezone="UTC")
    _register(scheduler)
    if settings.RUN_SCRAPE_ON_STARTUP:
        scheduler.add_job(scrape_and_predict, id="startup_scrape", max_instances=1)
    log.info("Blocking worker started; jobs registered")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Worker stopping")


if __name__ == "__main__":
    run_worker()
