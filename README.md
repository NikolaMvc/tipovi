# PredictAI — Football Match Prediction (local → static)

Football prediction app with a **fully local workflow**. You run **one command**; it
scrapes fixtures, computes predictions (**Dixon‑Coles → Poisson 7×7 → Monte Carlo
10 000 → value bets**), auto‑picks the day's safest tips, writes everything to
**static JSON**, and pushes to GitHub. **Vercel rebuilds the static frontend** on
every push. No server, no database, no Redis, no cron — free forever.

```
python run.py   →   scrape → predict → write /frontend/public/data/*.json → git push
                                                              ↓
                                              Vercel rebuilds static frontend
```

> Predictions refresh **only when you run the command**. The site shows the last
> snapshot. That's the intended trade‑off (no 24/7 server).

---

## Quick start

```bash
cp .env.example .env          # add FOOTBALL_DATA_API_KEY (free)
pip install -r backend/requirements.txt
python -c "from scrapling.cli import install; install.callback(force=False)"   # browsers

make run-local                # scrape + predict + write JSON (no push) — inspect first
make dev                      # http://localhost:3000 — preview the snapshot
make run                      # same as run-local, then git commit + push → Vercel
```

On Windows without `make`, run the underlying commands directly:
`python run.py --no-push`, `python run.py`, `cd frontend && npm run dev`.

---

## How it works

### `python run.py` (the only command you run)
| Step | What |
|---|---|
| 1 SCRAPE | football‑data.org `/v4/matches` for today + next 2 days (+ FlashScore fallback) |
| 2 PREDICT | per match: Dixon‑Coles λ → Poisson 7×7 (validated ~100 %) → Monte Carlo 10k → value bets |
| 3 RESULTS | finished matches from the last 3 days |
| 4 TIPS | auto **top‑20** safest picks/day, settled WON/LOST from results |
| 5 CLEANUP | drop prediction/result/tip files older than 3 days (rolling window) |
| 6 SAVE | write JSON + `index.json` into `frontend/public/data/` |
| 7 GIT | commit + push to `main` (skipped with `--no-push`) |

Flags: `--no-push` (local only), `--days N` (default 3), `--debug` (raw output).
A failure on one match/step is logged and the run continues; a summary prints at the end.

### Static data layout (`frontend/public/data/`, rolling 3 days)
```
predictions/<YYYY-MM-DD>.json   full prediction payloads for that day
results/<YYYY-MM-DD>.json       finished scores (for settling tips)
tips/<YYYY-MM-DD>.json          auto top‑20 tips for that day
index.json                      available days + last‑run timestamp
```

### Frontend (3 tabs, static — reads JSON directly)
- **Utakmice** — day selector (Danas/Sutra/Prekosutra) + match list; click → full detail
  (Poisson heatmap, Monte Carlo histogram, form, H2H, value bets, injuries, referee,
  weather, fatigue).
- **Tipovi** — the auto top‑20 picks, ranked by probability. Coloured automatically
  once results arrive: 🟢 WON · 🔴 LOST · 🟡 PENDING. No manual input.
- **Statistika** — win rate, settled count, ROI (when odds exist), performance timeline,
  by‑market breakdown — all computed from the tips files.

---

## Data sources

| Source | Role | Key |
|---|---|---|
| **football-data.org** | Primary — fixtures, standings (H/A split), form, H2H, results | ✅ free, **required for real data** |
| **FlashScore** | Fallback fixtures/form (leagues football‑data doesn't cover) | — |
| **SofaScore** | Best‑effort xG (its JSON API is blocked → graceful degradation) | — |
| **OpenWeatherMap** | Stadium weather → goal‑suppressing flag | optional |

Get the free key at <https://www.football-data.org/client/register> and put it in
`.env` as `FOOTBALL_DATA_API_KEY`. Without it, fixtures fall back to FlashScore and
predictions degrade to LOW confidence (every missing factor only lowers confidence —
nothing crashes).

`.env`:
```
FOOTBALL_DATA_API_KEY=...
OPENWEATHER_API_KEY=...      # optional
```

---

## Deploy (Vercel — static only, free)

Already linked to the repo. Vercel just serves static files (frontend + the JSON
snapshots), so there are **no backend env vars** to set.

- Root Directory: `frontend`
- Framework: **Vite** · Build: `npm run build` · Output: `dist`
- `frontend/public/data/` is copied into the build automatically; `vercel.json`
  keeps the SPA rewrite from touching `/data`.

Every `python run.py` pushes new JSON → Vercel redeploys in ~1 min.

---

## Tests
```bash
make test          # predictor + football-data mapping + jsonstore (17 tests)
make predict-test  # full sample prediction payload
make mc-test       # Monte Carlo sanity
```

## Tech stack
NumPy/SciPy · Scrapling (Camoufox stealth) · Playwright · React + Vite + Tailwind ·
recharts. Pure local Python pipeline → static JSON → Vercel.
