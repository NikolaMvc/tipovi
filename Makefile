.PHONY: dev down logs test migrate revision scrape-test predict-test mc-test fd-test frontend

# --- Local stack (Postgres + Redis + API + worker) ---
dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f backend worker

# --- Frontend ---
frontend:
	cd frontend && npm install && npm run dev

# --- Tests ---
test:
	python -m pytest backend/tests/ -q

# --- DB migrations ---
migrate:
	alembic -c backend/alembic.ini upgrade head

revision:
	alembic -c backend/alembic.ini revision --autogenerate -m "$(m)"

# --- Component smoke tests ---
scrape-test:
	python -m backend.scraper.sofascore --query "Real Madrid" --debug

fd-test:
	python -m backend.scraper.flashscore --league "LaLiga"

predict-test:
	python -m backend.predictor.demo

mc-test:
	python -c "from backend.predictor.montecarlo import simulate; r=simulate(1.7,1.1,n=10000,seed=42); print('home',r.home_win,'draw',r.draw,'away',r.away_win,'CI',r.confidence_interval)"
