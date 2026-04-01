FROM python:3.11-slim

# ── Dependências do sistema ───────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    wget \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependências Python ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Código da aplicação ───────────────────────────────────────────────────────
COPY app/ ./app/

# ── Diretórios de runtime ─────────────────────────────────────────────────────
RUN mkdir -p /tmp/yt_downloader/videos /tmp/yt_downloader/audios

# ── Usuário não-root ──────────────────────────────────────────────────────────
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app /tmp/yt_downloader
USER appuser

EXPOSE 8000

# ── Healthcheck nativo do Docker ──────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
