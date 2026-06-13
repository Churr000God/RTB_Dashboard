#!/usr/bin/env bash
set -euo pipefail

SCRIPT="scripts/levantar_dashboard.sh"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

[[ -f "$SCRIPT" ]] || fail "$SCRIPT no existe"
bash -n "$SCRIPT" || fail "$SCRIPT tiene errores de sintaxis"

required_patterns=(
  "docker compose up --build -d"
  "docker compose exec -T dashboard-rtb python3 -m py_compile"
  "docker compose exec -T dashboard-rtb python3 -m unittest discover -s tests -v"
  'BASE_URL="${RTB_BASE_URL:-http://localhost:8000}"'
  '$BASE_URL/'
  '$BASE_URL/api/dashboard/ventas'
  '$BASE_URL/api/dashboard/facturacion'
  '/docs'
  '/openapi.json'
)

for pattern in "${required_patterns[@]}"; do
  grep -Fq "$pattern" "$SCRIPT" || fail "falta el contrato: $pattern"
done

if grep -Fq "/api/actualizar-datos" "$SCRIPT"; then
  fail "el script no debe activar el webhook externo"
fi

printf 'PASS: contrato de %s verificado\n' "$SCRIPT"
