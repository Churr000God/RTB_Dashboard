#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="dashboard-rtb"
BASE_URL="http://localhost:8000"
MAX_ATTEMPTS=30
TMP_JSON=""
TMP_FACTURACION_JSON=""

cleanup() {
  if [[ -n "$TMP_JSON" ]]; then
    rm -f "$TMP_JSON"
  fi
  if [[ -n "$TMP_FACTURACION_JSON" ]]; then
    rm -f "$TMP_FACTURACION_JSON"
  fi
}

show_logs() {
  printf '\nUltimos logs de %s:\n' "$SERVICE" >&2
  docker compose logs --tail=120 "$SERVICE" >&2 || true
}

fail() {
  printf '\nERROR: %s\n' "$1" >&2
  show_logs
  exit 1
}

trap cleanup EXIT
cd "$ROOT_DIR"

command -v docker >/dev/null 2>&1 || {
  printf 'ERROR: docker no esta instalado o no esta disponible en PATH.\n' >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || {
  printf 'ERROR: curl no esta instalado o no esta disponible en PATH.\n' >&2
  exit 1
}

printf 'Levantando Dashboard RTB con Docker Compose...\n'
docker compose up --build -d

printf 'Esperando respuesta de %s/ ...\n' "$BASE_URL"
ready=false
for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  if curl --silent --show-error --fail --output /dev/null "$BASE_URL/"; then
    ready=true
    break
  fi
  sleep 1
done

[[ "$ready" == "true" ]] || fail "el dashboard no respondio despues de ${MAX_ATTEMPTS} intentos"

printf 'Validando sintaxis Python dentro del contenedor...\n'
docker compose exec -T dashboard-rtb python3 -m py_compile \
  rtb_web.py \
  rtb_analisis.py || fail "fallo la compilacion Python"

printf 'Ejecutando pruebas unitarias dentro del contenedor...\n'
docker compose exec -T dashboard-rtb python3 -m unittest discover -s tests -v ||
  fail "fallaron las pruebas unitarias"

printf 'Verificando UI, API de ventas y API de facturacion...\n'
curl --silent --show-error --fail --output /dev/null "$BASE_URL/" ||
  fail "la portada no respondio correctamente"

TMP_JSON="$(mktemp)"
curl --silent --show-error --fail --output "$TMP_JSON" "$BASE_URL/api/dashboard/ventas" ||
  fail "la API de ventas no respondio correctamente"

python3 -m json.tool "$TMP_JSON" >/dev/null ||
  fail "la API de ventas no devolvio JSON valido"

TMP_FACTURACION_JSON="$(mktemp)"
curl --silent --show-error --fail --output "$TMP_FACTURACION_JSON" "$BASE_URL/api/dashboard/facturacion" ||
  fail "la API de facturacion no respondio correctamente"

python3 -m json.tool "$TMP_FACTURACION_JSON" >/dev/null ||
  fail "la API de facturacion no devolvio JSON valido"

printf '\nDashboard RTB disponible:\n'
printf 'Dashboard:    %s/\n' "$BASE_URL"
printf 'API ventas:       %s/api/dashboard/ventas\n' "$BASE_URL"
printf 'API facturacion:  %s/api/dashboard/facturacion\n' "$BASE_URL"
printf 'API docs:     %s/docs\n' "$BASE_URL"
printf 'OpenAPI JSON: %s/openapi.json\n' "$BASE_URL"
