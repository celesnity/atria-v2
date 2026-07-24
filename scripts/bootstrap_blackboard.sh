#!/usr/bin/env bash
# Idempotent: ensures a "minder" project + "minder" blackboard exist on
# blackboard-server, then writes BLACKBOARD_PROJECT_ID / BLACKBOARD_ID into .env.
# Requires: curl, jq. Run after blackboard-server is healthy (see Task 1),
# and re-run any time .env's BLACKBOARD_ID goes stale (e.g. after
# `docker compose down -v` wipes blackboard-db's volume).
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env"
[ -f "$ENV_FILE" ] || { echo "No .env found — copy .env.example first." >&2; exit 1; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

BASE_URL="http://localhost:${BLACKBOARD_HOST_PORT:-8090}"
API_KEY="${BLACKBOARD_API_KEY:-dev-key}"

echo "Waiting for blackboard-server at $BASE_URL ..."
ready=0
for _ in $(seq 1 30); do
  if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  echo "blackboard-server not healthy at $BASE_URL after 60s" >&2
  exit 1
fi

PROJECT_ID=$(curl -sf "$BASE_URL/api/v1/projects" -H "x-api-key: $API_KEY" \
  | jq -r '.[] | select(.name=="minder") | .id' | head -n1)

if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(curl -sf -X POST "$BASE_URL/api/v1/projects" -H "x-api-key: $API_KEY" \
    -H "content-type: application/json" -d '{"name":"minder"}' | jq -r '.id')
  echo "Created project 'minder' ($PROJECT_ID)"
else
  echo "Found existing project 'minder' ($PROJECT_ID)"
fi

BOARD_ID=$(curl -sf "$BASE_URL/api/v1/blackboards?project_id=$PROJECT_ID" -H "x-api-key: $API_KEY" \
  | jq -r '.[] | select(.name=="minder") | .id' | head -n1)

if [ -z "$BOARD_ID" ]; then
  BOARD_ID=$(curl -sf -X POST "$BASE_URL/api/v1/blackboards" -H "x-api-key: $API_KEY" \
    -H "content-type: application/json" \
    -d "{\"project_id\":\"$PROJECT_ID\",\"name\":\"minder\"}" | jq -r '.id')
  echo "Created blackboard 'minder' ($BOARD_ID)"
else
  echo "Found existing blackboard 'minder' ($BOARD_ID)"
fi

set_env_var() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

set_env_var "BLACKBOARD_PROJECT_ID" "$PROJECT_ID"
set_env_var "BLACKBOARD_ID" "$BOARD_ID"

echo "Wrote BLACKBOARD_PROJECT_ID=$PROJECT_ID and BLACKBOARD_ID=$BOARD_ID to $ENV_FILE"
