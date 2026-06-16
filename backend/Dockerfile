# Playwright base image ships Chromium + all system libs the stealth browser needs.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# --- Python deps ---
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# --- Scraping browsers (Chromium for Playwright + Camoufox for Scrapling stealth) ---
RUN playwright install chromium && \
    python -c "from scrapling.cli import install; install.callback(force=False)" || true

# --- App source ---
COPY backend ./backend
COPY README.md ./README.md

EXPOSE 8000

# Run migrations then launch the API. Worker uses a different command (see compose / Railway).
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
