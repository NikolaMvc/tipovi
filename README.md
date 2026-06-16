# PredictAI — Football Match Prediction

Professional football prediction web app. A background worker scrapes data,
computes predictions with **Poisson + Dixon‑Coles + Monte Carlo**, and stores the
finished results in PostgreSQL. The API only **reads** pre‑computed predictions, so
the user **never waits** when opening the app.

```
WORKER (cron, every 6h):  scrape → λ → Poisson → Monte Carlo → store in DB
API   (on request):       read finished prediction from DB → instant response
```

---

## ⚠️ Important note on data sources

The spec's primary source, **`api.sofascore.com`, is hard‑blocked** (HTTP 403
`challenge`). This was verified exhaustively with Scrapling — plain `Fetcher`,
`impersonate` (curl_cffi TLS), `StealthyFetcher`, Cloudflare solver, in‑page
same‑origin `fetch`, `page.goto`, and full httpOnly cookie‑jar replay with a
matching User‑Agent. Solving Cloudflare on `www.sofascore.com` yields **no
`cf_clearance`** for the API subdomain, and the API never serves a solvable
challenge page. No residential proxy is available to bypass it.

The app therefore uses a **pluggable provider** with graceful degradation:

| Source | Role | Needs key |
|---|---|---|
| **football-data.org** | Primary structured backbone — fixtures, standings (home/away split), form, H2H, results | ✅ free key (recommended) |
| **FlashScore** | Fixtures/form via stealth‑browser DOM scraping (fallback when no key) | — |
| **SofaScore** | Best‑effort xG enrichment via website `__NEXT_DATA__` (API attempted but usually blocked) | — |
| **OpenWeatherMap** | Stadium weather → goal‑suppressing flag | ✅ free key (optional) |

> **To get real data, add a free `FOOTBALL_DATA_API_KEY`** (sign up at
> <https://www.football-data.org/client/register>). Without it the app falls back
> to FlashScore (reduced data → lower confidence). Every missing field only lowers
> the confidence score; nothing crashes.

---

## Architecture

```
backend/
  scraper/      data acquisition (footballdata, flashscore, sofascore, weather, provider)
  predictor/    lambda_calc → poisson → montecarlo → engine → value
  models/       SQLAlchemy ORM + Alembic migrations
  worker/       APScheduler cron jobs (scrape/refresh/settle)
  main.py       FastAPI — reads predictions from DB (instant)
  store.py      persistence + tip settlement + stats
  cache.py      graceful Redis cache (no‑op if Redis down)
frontend/       React + Vite + Tailwind (3 tabs, dark/neon design)
```

### Prediction pipeline
1. **λ (lambda_calc)** — Dixon‑Coles attack/defense strengths × league baselines,
   modified by form (last‑5 weighted), xG correction, fatigue, injuries, weather.
2. **Poisson (poisson)** — 7×7 scoreline matrix with the Dixon‑Coles low‑score
   correction (ρ=‑0.13). Validated to sum to ~100 %.
3. **Monte Carlo (montecarlo)** — 10,000 vectorised sims with red cards / penalties
   / fatigue late goals. Seedable → reproducible.
4. **Engine** — blends `(Poisson + Monte Carlo) / 2`, computes a confidence score
   from how many of the 7 factors (form, H2H, xG, injuries, referee, weather,
   fatigue) were available, and lists the missing ones.
5. **Value bets** — `value = our_prob − implied_prob`, Kelly + half‑Kelly staking.

---

## Local development

### Prerequisites
- Python 3.11+ (tested on 3.13), Node 18+, Docker (for the full stack).

### Option A — full stack with Docker
```bash
cp .env.example .env          # add FOOTBALL_DATA_API_KEY / OPENWEATHER_API_KEY
make dev                      # Postgres + Redis + API + worker
make frontend                 # separate terminal → http://localhost:3000
```

### Option B — backend without Docker (SQLite)
```bash
pip install -r backend/requirements.txt
python -c "from scrapling.cli import install; install.callback(force=False)"   # browsers
export DATABASE_URL="sqlite:///./tipovi.db"
make migrate                                  # or rely on init_db() at startup
uvicorn backend.main:app --reload             # http://localhost:8000/docs
python -m backend.worker.scheduler            # separate terminal (background jobs)
```

### Handy commands
```bash
make test          # pytest (predictor + footballdata + api)
make predict-test  # full sample prediction payload
make mc-test       # Monte Carlo sanity output
make scrape-test   # SofaScore --debug (shows the 403 block + website fallback)
make fd-test       # FlashScore DOM extraction
```

---

## Environment variables

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | all | Postgres in prod, `sqlite:///./tipovi.db` locally. `postgres://` is auto‑normalized. |
| `REDIS_URL` | API | Optional; caching disabled if unreachable. |
| `FOOTBALL_DATA_API_KEY` | scraper/worker | **Recommended** — unlocks reliable data. |
| `OPENWEATHER_API_KEY` | scraper | Optional weather factor. |
| `CORS_ORIGINS` | API | Comma‑separated allowed origins. |
| `MC_SIMULATIONS`, `MC_SEED` | predictor | Sim count / reproducible seed. |
| `RUN_WORKER_IN_API` | API | `true` runs the scheduler in‑process (single‑dyno). |
| `VITE_API_URL` | frontend | Backend base URL (set on Vercel). |

---

## Deploy

### Backend + Worker + DB + Redis → Railway
1. `railway init` (or create a project in the dashboard) and link this repo.
2. Add the **PostgreSQL** and **Redis** plugins → they provide `DATABASE_URL` and
   `REDIS_URL` automatically.
3. **Web service**: uses `railway.json` (Dockerfile build). It runs Alembic
   migrations then `uvicorn`. Set vars `FOOTBALL_DATA_API_KEY`,
   `OPENWEATHER_API_KEY`, `CORS_ORIGINS` (your Vercel URL).
4. **Worker service**: add a second service from the same repo with start command
   `python -m backend.worker.scheduler` (same env, same Dockerfile).
   ```bash
   railway up                       # deploy
   railway variables --set FOOTBALL_DATA_API_KEY=xxxx
   ```
5. Grab the public web URL (e.g. `https://tipovi-production.up.railway.app`).

### Frontend → Vercel
```bash
cd frontend
vercel                       # link project, framework auto-detected (Vite)
vercel env add VITE_API_URL  # → your Railway backend URL
vercel --prod
```
Or in the Vercel dashboard: **Import repo → Root Directory `frontend` →
Build `npm run build` → Output `dist`**, then add `VITE_API_URL`. `vercel.json`
already configures the SPA rewrite.

---

## Tech stack
FastAPI · SQLAlchemy 2 · Alembic · APScheduler · NumPy/SciPy · Scrapling
(Camoufox stealth) · Playwright · Redis · React + Vite + Tailwind · recharts.
