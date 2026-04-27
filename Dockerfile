# ── Stage 1: install dependencies ──────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

# pandas/numpy/Pillow/uvicorn all ship as binary wheels — no compiler needed.
# Only curl-CA-bundle and a minimal libc are required by the slim base.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime image ──────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from the build stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source (venv/, data/, __pycache__ excluded via .dockerignore)
COPY . .

# The data directory is mounted as a volume at runtime so the DB and icon
# cache survive container restarts. Create it here as a safe fallback.
RUN mkdir -p data

# Non-root user — better security practice
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "main_web.py"]
