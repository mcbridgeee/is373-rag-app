# Session Notes: FastAPI + SQLite FTS5 + Chroma, served on port 8000.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data && chown app:app /data && chmod 700 /data

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

USER app
# Bake the embedding model (all-MiniLM-L6-v2, ONNX) into the image so the
# server never downloads it at runtime.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as E; E()(['warm up'])"

COPY --chown=app:app app ./app
COPY --chown=app:app corpus ./corpus
COPY --chown=app:app scripts ./scripts

ENV APP_MODE=production \
    APP_DATABASE=/data/app.sqlite3 \
    APP_CORPUS=/srv/corpus

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request as u; r=u.Request('http://127.0.0.1:8000/health', headers={'Host': os.environ['APP_ORIGIN'].split('//')[1]}); u.urlopen(r, timeout=4)"

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
