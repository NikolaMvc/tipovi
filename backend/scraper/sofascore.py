"""SofaScore scraper — BEST EFFORT.

IMPORTANT: api.sofascore.com is hard-protected (HTTP 403 "challenge") and could
not be reached from our test environment by any scrapling method (plain Fetcher,
impersonate, StealthyFetcher, cookie-harvest replay, in-page fetch). This module
therefore:

  1. Tries the JSON API anyway via a cf_clearance cookie harvested from the main
     site (works only if your egress IP / environment is whitelisted enough).
  2. Falls back to rendering the public website and reading the __NEXT_DATA__
     blob for whatever static data is embedded (team info, squad).

Everything degrades to ``None`` so the rest of the pipeline keeps working. Use
``python -m backend.scraper.sofascore --debug --query "Real Madrid"`` to inspect
raw responses and confirm the current endpoint structure.
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Optional

from backend.scraper.utils import (
    fetch_browser, log, normalize_team_name, random_ua,
)

API = "https://api.sofascore.com/api/v1"
WWW = "https://www.sofascore.com"


class SofaScoreClient:
    def __init__(self):
        self._cookies: Optional[dict] = None
        self._ua: Optional[str] = None

    # ------------------------------------------------------------------ #
    def _harvest_clearance(self) -> bool:
        """Solve Cloudflare on www.sofascore.com and cache cookies + UA."""
        info: dict = {}

        def grab(page):
            try:
                info["ua"] = page.evaluate("() => navigator.userAgent")
                info["cookies"] = page.context.cookies()
            except Exception:
                pass
            return page

        r = fetch_browser(f"{WWW}/", solve_cloudflare=True, page_action=grab)
        if not r:
            return False
        self._ua = info.get("ua")
        cks = info.get("cookies") or []
        self._cookies = {c["name"]: c["value"] for c in cks}
        return bool(self._cookies)

    def api_get(self, path: str, debug: bool = False):
        """Attempt a SofaScore API call. Returns parsed JSON or None."""
        from scrapling.fetchers import Fetcher
        if self._cookies is None:
            self._harvest_clearance()
        url = f"{API}{path}"
        headers = {
            "User-Agent": self._ua or random_ua(),
            "Referer": f"{WWW}/",
            "Origin": WWW,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            r = Fetcher.get(url, headers=headers, cookies=self._cookies or {},
                            impersonate="chrome", timeout=25)
            if debug:
                body = r.body if isinstance(r.body, (bytes, str)) else str(r.body)
                print(f"[DEBUG] GET {url}\n  status={r.status}\n  body[:500]={str(body)[:500]}\n")
            if r.status == 200:
                return r.json()
            log.info("sofascore api %s -> HTTP %s (blocked/unavailable)", path, r.status)
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("sofascore api %s error: %s", path, exc)
            return None

    # ------------------------------------------------------------------ #
    def search_team(self, name: str, debug: bool = False) -> Optional[dict]:
        data = self.api_get(f"/search/all?q={name}", debug=debug)
        if not data:
            return None
        for item in data.get("results", []):
            if item.get("type") == "team":
                ent = item.get("entity", {})
                if normalize_team_name(ent.get("name")) and ent.get("id"):
                    return {"id": ent["id"], "name": ent.get("name")}
        return None

    def team_next_event(self, team_id: int, debug: bool = False) -> Optional[dict]:
        data = self.api_get(f"/team/{team_id}/events/next/0", debug=debug)
        events = (data or {}).get("events", [])
        return events[0] if events else None

    def event_statistics(self, event_id: int, debug: bool = False) -> Optional[dict]:
        return self.api_get(f"/event/{event_id}/statistics", debug=debug)

    def event_lineups(self, event_id: int, debug: bool = False) -> Optional[dict]:
        return self.api_get(f"/event/{event_id}/lineups", debug=debug)

    def event_odds(self, event_id: int, debug: bool = False) -> Optional[dict]:
        return self.api_get(f"/event/{event_id}/odds/1/all", debug=debug)

    # ------------------------------------------------------------------ #
    def team_page_data(self, slug: str, team_id: int) -> Optional[dict]:
        """Website fallback: extract the __NEXT_DATA__ JSON from a team page."""
        r = fetch_browser(f"{WWW}/football/team/{slug}/{team_id}", solve_cloudflare=True)
        if not r:
            return None
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.html_content, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1)).get("props", {}).get("pageProps", {})
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# Debug CLI
# --------------------------------------------------------------------------- #
def _main():
    parser = argparse.ArgumentParser(description="SofaScore scraper debug tool")
    parser.add_argument("--query", default="Real Madrid", help="team to search")
    parser.add_argument("--debug", action="store_true", help="print raw responses")
    args = parser.parse_args()

    client = SofaScoreClient()
    print(f"== Searching SofaScore API for '{args.query}' ==")
    team = client.search_team(args.query, debug=args.debug)
    if team:
        print(f"  Found: {team}")
        ev = client.team_next_event(team["id"], debug=args.debug)
        print(f"  Next event: {ev.get('id') if ev else None}")
    else:
        print("  API unreachable (expected if SofaScore is blocking). Trying website fallback...")
        pp = client.team_page_data("real-madrid", 2829)
        if pp:
            td = pp.get("teamDetails", {})
            print(f"  Website __NEXT_DATA__ team: {td.get('name')} | venue: "
                  f"{td.get('venue', {}).get('stadium', {}).get('name')}")
        else:
            print("  Website fallback also returned nothing.")


if __name__ == "__main__":
    _main()
