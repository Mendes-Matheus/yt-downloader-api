#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COOKIE_FILE="${PROJECT_DIR}/cookies.txt"
TMP_COOKIE_FILE="${PROJECT_DIR}/cookies.tmp.txt"
FILTERED_COOKIE_FILE="${PROJECT_DIR}/cookies.filtered.tmp.txt"
TARGET_URL="https://youtu.be/kqjR2CYlUms?si=dILK1G3Gzc6CVTGk"
COOKIE_BROWSER="${1:-chrome}"
COOKIE_PROFILE="${2:-}"

cleanup() {
  rm -f "${TMP_COOKIE_FILE}"
  rm -f "${FILTERED_COOKIE_FILE}"
}
trap cleanup EXIT

filter_relevant_cookies() {
  awk '
    NR == 1 { print; next }
    /^#HttpOnly_/ {
      domain = $1
      sub(/^#HttpOnly_/, "", domain)
      if (domain ~ /(^|.*\.)youtube\.com$/ || domain ~ /(^|.*\.)google\.com$/) {
        print
      }
      next
    }
    /^#/ || NF == 0 { print; next }
    {
      domain = $1
      if (domain ~ /(^|.*\.)youtube\.com$/ || domain ~ /(^|.*\.)google\.com$/) {
        print
      }
    }
  ' "${TMP_COOKIE_FILE}" > "${FILTERED_COOKIE_FILE}"

  mv "${FILTERED_COOKIE_FILE}" "${TMP_COOKIE_FILE}"
}

echo "[update_cookies] Iniciando exportacao de cookies do navegador '${COOKIE_BROWSER}'..."
if [[ -n "${COOKIE_PROFILE}" ]]; then
  echo "[update_cookies] Usando perfil '${COOKIE_PROFILE}'."
  COOKIE_BROWSER_ARG="${COOKIE_BROWSER}:${COOKIE_PROFILE}"
else
  COOKIE_BROWSER_ARG="${COOKIE_BROWSER}"
fi

cd "${PROJECT_DIR}"

YTDLP_EXIT_CODE=0
if yt-dlp \
  --skip-download \
  --cookies-from-browser "${COOKIE_BROWSER_ARG}" \
  --cookies "${TMP_COOKIE_FILE}" \
  "${TARGET_URL}"; then
  :
else
  YTDLP_EXIT_CODE=$?
  echo "[update_cookies] Aviso: yt-dlp falhou ao validar a URL de teste, mas pode ter exportado os cookies mesmo assim."
fi

if [[ ! -s "${TMP_COOKIE_FILE}" ]]; then
  echo "[update_cookies] Falha: yt-dlp nao gerou arquivo temporario de cookies."
  exit "${YTDLP_EXIT_CODE:-1}"
fi

echo "[update_cookies] Filtrando cookies relevantes para YouTube/Google..."
filter_relevant_cookies

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
if [[ "${YTDLP_EXIT_CODE}" -ne 0 ]]; then
  echo "[update_cookies] Aviso: a URL de teste falhou, mas os cookies foram exportados e validados."
fi
echo "[update_cookies] Concluido."
