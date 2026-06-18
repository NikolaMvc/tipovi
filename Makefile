.PHONY: run run-local dev build test scrape-test fd-test mc-test predict-test

# --- The one command: scrape + predict + save JSON + git push (Vercel rebuilds) ---
run:
	python run.py

# Same, but local only (no git push) — for testing before publishing
run-local:
	python run.py --no-push

# Fast pass: colour tips WON/LOST from finished results + push (no scrape/predict)
settle:
	python run.py --settle-only

# --- Frontend ---
dev:
	cd frontend && npm install && npm run dev

build:
	cd frontend && npm run build

# --- Tests ---
test:
	python -m pytest backend/tests/ -q

# --- Component smoke tests ---
mc-test:
	python -c "from backend.predictor.montecarlo import simulate; r=simulate(1.7,1.1,n=10000,seed=42); print('home',r.home_win,'draw',r.draw,'away',r.away_win,'CI',r.confidence_interval)"

predict-test:
	python -m backend.predictor.demo

scrape-test:
	python -m backend.scraper.sofascore --query "Real Madrid" --debug

fd-test:
	python -m backend.scraper.flashscore --league "LaLiga"
