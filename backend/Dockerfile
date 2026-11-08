# TripAura backend - works on Hugging Face Spaces (Docker), Render, Railway, Fly.io or any Docker host.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/home/user/app/data \
    HOME=/home/user

# Hugging Face Spaces runs containers as uid 1000; using the same user works everywhere.
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=user app ./app
COPY --chown=user scripts ./scripts
USER user

# Bake the city index, embedding model and DuckDB extension into the image (fast, offline-safe start).
RUN python scripts/prefetch.py

# Hugging Face Spaces expects 7860; Render/Railway/Fly inject $PORT.
ENV PORT=7860
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"7860\")}/api/health')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
