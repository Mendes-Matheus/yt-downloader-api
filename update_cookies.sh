#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COOKIE_FILE="${PROJECT_DIR}/cookies.txt"
TMP_COOKIE_FILE="${PROJECT_DIR}/cookies.tmp.txt"
TARGET_URL="https://www.youtube.com/watch?v=BaW_jenozKc"
COOKIE_BROWSER="${1:-chrome}"
COOKIE_PROFILE="${2:-}"

cleanup() {
  rm -f "${TMP_COOKIE_FILE}"
}
trap cleanup EXIT

echo "[update_cookies] Iniciando exportacao de cookies do navegador '${COOKIE_BROWSER}'..."
if [[ -n "${COOKIE_PROFILE}" ]]; then
  echo "[update_cookies] Usando perfil '${COOKIE_PROFILE}'."
  COOKIE_BROWSER_ARG="${COOKIE_BROWSER}:${COOKIE_PROFILE}"
else
  COOKIE_BROWSER_ARG="${COOKIE_BROWSER}"
fi

cd "${PROJECT_DIR}"

yt-dlp \
  --skip-download \
  --cookies-from-browser "${COOKIE_BROWSER_ARG}" \
  --cookies "${TMP_COOKIE_FILE}" \
  "${TARGET_URL}"

if ! grep -q "^# Netscape HTTP Cookie File" "${TMP_COOKIE_FILE}"; then
  echo "[update_cookies] Falha: arquivo exportado nao esta no formato Netscape."
  exit 1
fi

if ! grep -Eq '(^|\.)youtube\.com' "${TMP_COOKIE_FILE}"; then
  echo "[update_cookies] Falha: nao foram encontrados cookies de youtube.com."
  echo "[update_cookies] Abra o YouTube no navegador '${COOKIE_BROWSER}', faca login e rode novamente."
  exit 1
fi

mv "${TMP_COOKIE_FILE}" "${COOKIE_FILE}"
echo "[update_cookies] Cookies atualizados em ${COOKIE_FILE} (formato Netscape valido)."
echo "[update_cookies] Concluido."
