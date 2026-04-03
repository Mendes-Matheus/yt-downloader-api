#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# renew_cookies.sh – Renova cookies e reinicia o container se necessário
#
# Uso: ./renew_cookies.sh [browser] [perfil]
#   browser : chrome | firefox  (padrão: chrome)
#   perfil  : nome do perfil    (padrão: "Default")
#
# Instale no cron do host (a cada 6 horas):
#   0 */6 * * * /opt/yout-downloader/renew_cookies.sh chrome "Default" >> /var/log/renew_cookies.log 2>&1
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BROWSER="${1:-chrome}"
PROFILE="${2:-Default}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COOKIES_FILE="${SCRIPT_DIR}/cookies.txt"
CONTAINER_NAME="${CONTAINER_NAME:-downloader}"   # nome do container docker-compose
# Valida variáveis obrigatórias antes de qualquer operação
: "${INTERNAL_API_TOKEN:?Variável INTERNAL_API_TOKEN não definida}"

log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*"; }

# ── 1. Exportar cookies via update_cookies.sh original ───────────────────────
log "Exportando cookies do $BROWSER (perfil: $PROFILE)…"
bash "${SCRIPT_DIR}/update_cookies.sh" "$BROWSER" "$PROFILE"

# ── 2. Validar formato Netscape ───────────────────────────────────────────────
if [[ ! -f "$COOKIES_FILE" ]]; then
  log "ERRO: $COOKIES_FILE não foi criado"
  exit 1
fi

FIRST_LINE=$(head -n 1 "$COOKIES_FILE")
if [[ "$FIRST_LINE" != "# Netscape HTTP Cookie File" ]]; then
  log "ERRO: $COOKIES_FILE não está no formato Netscape (primeira linha: '$FIRST_LINE')"
  exit 1
fi

# ── 3. Verificar se há cookies do YouTube ────────────────────────────────────
if ! grep -q "youtube\.com" "$COOKIES_FILE"; then
  log "AVISO: Nenhum cookie de youtube.com encontrado em $COOKIES_FILE"
  exit 1
fi

log "Cookies válidos. $(grep -c 'youtube\.com' "$COOKIES_FILE") cookies do YouTube encontrados."

# ── 4. Reiniciar container para recarregar o volume montado ──────────────────
if command -v docker &>/dev/null; then
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "Recarregando cookies via API (POST /admin/reload-cookies)…"
    if RESP="$(curl -sf -X POST "http://localhost:8000/admin/reload-cookies" -H "X-Internal-Token: ${INTERNAL_API_TOKEN:?Variável INTERNAL_API_TOKEN não definida}")"; then
      log "Cookies recarregados com sucesso. Resposta: ${RESP}"
    else
      log "ERRO: Falha ao recarregar cookies via API."
      exit 1
    fi
  else
    log "AVISO: Container '$CONTAINER_NAME' não está rodando. Pulando reinício."
  fi
else
  log "AVISO: Docker não encontrado. Reinicie o container manualmente."
fi

log "Renovação de cookies concluída."
