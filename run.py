#!/usr/bin/env python
"""PredictAI — single local "run" command.

    python run.py [--no-push] [--days N] [--debug]

Steps:
  1. SCRAPE    upcoming fixtures (today + next N-1 days) via football-data.org
               (+ FlashScore fallback for leagues it doesn't cover)
  2. PREDICT   Dixon-Coles -> Poisson 7x7 -> Monte Carlo 10k -> value bets
  3. RESULTS   finished matches from the last ROLLING_DAYS days
  4. TIPS      auto top-N safest tips per day, settled (WON/LOST) from results
  5. CLEANUP   drop prediction/result/tip files older than the rolling window
  6. SAVE      write JSON snapshots + index.json into frontend/public/data/
  7. GIT       commit + push to main (Vercel rebuilds) unless --no-push

A failure on one match/step is logged and the run continues; a summary of errors
is printed at the end.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

from backend.config import settings, DATA_DIR
from backend.scraper.provider import DataProvider
from backend.scraper.footballdata import FootballDataClient
from backend.predictor.engine import predict
from backend.predictor.poisson import compute_poisson  # noqa: F401 (kept explicit)
from backend import jsonstore as js
from backend.scraper.utils import get_logger

log = get_logger("run")
ERRORS: list[str] = []


def _day(dt) -> str:
    return (dt.date().isoformat() if dt else datetime.now(timezone.utc).date().isoformat())


def step_scrape(days: int, debug: bool) -> list:
    print(f"\n[1/7 SCRAPE] fixtures for today + {days - 1} day(s)…")
    provider = DataProvider()
    print(f"  primary source: {provider.primary_source}")
    try:
        matches = provider.collect_upcoming(days=days, require_odds=settings.REQUIRE_ODDS)
    except Exception as exc:  # noqa: BLE001
        ERRORS.append(f"scrape: {exc}")
        matches = []
    by_day: dict[str, list] = defaultdict(list)
    for m in matches:
        by_day[_day(m.match_date)].append(m)
    for d in sorted(by_day):
        print(f"  {d}: {len(by_day[d])} matches")
    if not matches:
        print("  (no fixtures — empty snapshot; add FOOTBALL_DATA_API_KEY for real data)")
    if debug and matches:
        print("  [debug] first match:", matches[0].home_team, "vs", matches[0].away_team,
              "| sources:", matches[0].data_sources)
    return matches


def step_predict(matches: list) -> dict[str, list[dict]]:
    print(f"\n[2/7 PREDICT] computing {len(matches)} prediction(s)…")
    by_day: dict[str, list[dict]] = defaultdict(list)
    for i, m in enumerate(matches, 1):
        try:
            resp = predict(m)
            # carry the fixture id so tips/results/predictions link by the same key
            resp["match"]["event_id"] = m.event_id
            # sanity: Poisson matrix must sum ~100%
            if abs(resp.get("poisson_matrix_sum", 0) - 100.0) > 1.0:
                log.warning("matrix sum off for %s vs %s: %s",
                            m.home_team, m.away_team, resp.get("poisson_matrix_sum"))
            by_day[_day(m.match_date)].append(resp)
        except Exception as exc:  # noqa: BLE001
            ERRORS.append(f"predict {m.home_team} vs {m.away_team}: {exc}")
        if i % 5 == 0 or i == len(matches):
            print(f"  {i}/{len(matches)} processed")
    return by_day


def step_results(days_back: int, debug: bool) -> dict[str, list[dict]]:
    print(f"\n[3/7 RESULTS] finished matches, last {days_back} day(s)…")
    fd = FootballDataClient()
    by_day: dict[str, list[dict]] = defaultdict(list)
    if not fd.enabled:
        print("  (no football-data key — skipping result fetch)")
        return by_day
    try:
        for mt in fd.finished_results(days_back=days_back):
            ft = mt.get("score", {}).get("fullTime", {})
            hg, ag = ft.get("home"), ft.get("away")
            if hg is None or ag is None:
                continue
            dt = mt.get("utcDate", "")[:10] or _day(None)
            by_day[dt].append({
                "id": str(mt.get("id")),
                "home_team": mt.get("homeTeam", {}).get("name"),
                "away_team": mt.get("awayTeam", {}).get("name"),
                "home_goals": hg, "away_goals": ag, "status": "FINISHED",
            })
    except Exception as exc:  # noqa: BLE001
        ERRORS.append(f"results: {exc}")
    total = sum(len(v) for v in by_day.values())
    print(f"  {total} finished result(s) across {len(by_day)} day(s)")
    return by_day


def step_save_and_tips(preds_by_day, results_by_day, debug):
    print("\n[4/7 TIPS] + [6/7 SAVE] generating tips and writing snapshots…")
    # Save results first so settlement can see them.
    for d, results in results_by_day.items():
        js.save_results(d, results)
    results_by_id = js.all_results_by_id()

    for d, responses in preds_by_day.items():
        js.save_predictions(d, responses)  # assigns match ids
        tips = js.generate_top_tips(responses)
        settled = js.settle_tips(tips, results_by_id)
        js.save_tips(d, tips)
        print(f"  {d}: {len(responses)} predictions, {len(tips)} tips ({settled} settled)")

    # Also settle/re-save tips for prior days now that new results arrived.
    for f in js.TIPS_DIR.glob("*.json") if js.TIPS_DIR.exists() else []:
        d = f.stem
        if d in preds_by_day:
            continue
        data = js._read(f) or {}
        tips = data.get("tips", [])
        if tips and js.settle_tips(tips, results_by_id):
            js.save_tips(d, tips)
            print(f"  {d}: re-settled prior-day tips")


def step_cleanup():
    print("\n[5/7 CLEANUP] enforcing rolling window…")
    removed = js.cleanup_old()
    print(f"  removed {removed} file(s) older than {settings.ROLLING_DAYS} days")


def step_index():
    idx = js.write_index()
    print(f"  index.json: {len(idx['prediction_days'])} prediction day(s), "
          f"last run {idx['last_run']}")


def step_git(no_push: bool):
    print("\n[7/7 GIT]")
    if no_push:
        print("  --no-push set; skipping commit/push.")
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        subprocess.run(["git", "add", "-A"], check=True)
        res = subprocess.run(["git", "commit", "-m", f"update predictions {stamp}"],
                             capture_output=True, text=True)
        if res.returncode != 0 and "nothing to commit" in (res.stdout + res.stderr):
            print("  nothing changed; not pushing.")
            return
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("  Push successful. Vercel will rebuild in ~1 min.")
    except Exception as exc:  # noqa: BLE001
        ERRORS.append(f"git: {exc}")
        print(f"  git step failed: {exc}")


def main():
    parser = argparse.ArgumentParser(description="PredictAI local run")
    parser.add_argument("--no-push", action="store_true", help="don't git commit/push")
    parser.add_argument("--days", type=int, default=settings.LOOKAHEAD_DAYS, help="days ahead")
    parser.add_argument("--debug", action="store_true", help="verbose raw output")
    args = parser.parse_args()

    print(f"=== PredictAI run @ {datetime.now().strftime('%Y-%m-%d %H:%M')} "
          f"(days={args.days}) ===")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    matches = step_scrape(args.days, args.debug)
    preds_by_day = step_predict(matches)
    results_by_day = step_results(settings.ROLLING_DAYS, args.debug)
    step_save_and_tips(preds_by_day, results_by_day, args.debug)
    step_cleanup()
    step_index()
    step_git(args.no_push)

    print("\n=== DONE ===")
    if ERRORS:
        print(f"{len(ERRORS)} non-fatal error(s):")
        for e in ERRORS[:20]:
            print("  -", e)
    else:
        print("No errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
