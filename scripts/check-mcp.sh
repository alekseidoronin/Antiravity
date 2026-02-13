#!/bin/bash
# Проверка доступности MCP-серверов
# Запуск: ./check-mcp.sh
# По расписанию: launchd (см. README ниже)

LOG_DIR="${LOG_DIR:-$HOME/Documents/CURSOR/scripts/logs}"
LOG_FILE="$LOG_DIR/mcp-check.log"
mkdir -p "$LOG_DIR"

NODE_BIN="/Users/alekseidoronin/Documents/CURSOR/nodejs/bin"
export PATH="$NODE_BIN:/usr/bin:/bin:/usr/sbin:/sbin"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
ok()  { log "OK   $1"; }
fail() { log "FAIL $1"; }

log "--- MCP check ---"

# URL: проверяем HTTP-ответ
check_url() {
  local name="$1" url="$2" header="$3"
  local code
  if [[ -n "$header" ]]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "$header" "$url" 2>/dev/null)
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null)
  fi
  if [[ "$code" =~ ^2 ]]; then ok "$name (HTTP $code)"; else fail "$name (HTTP $code)"; fi
}

# Команда: запускаем в фоне, через 3 сек проверяем, жив ли процесс
check_cmd() {
  local name="$1"
  shift
  "$@" & pid=$!
  sleep 3
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
    ok "$name (started)"
  else
    wait "$pid" 2>/dev/null
    fail "$name (exited early)"
  fi
}

check_url "context7" "https://mcp.context7.com/mcp" "CONTEXT7_API_KEY: ctx7sk-0182a948-b98d-409a-8581-c91dac5db544"
check_url "supabase" "https://mcp.supabase.com/mcp"

# stdio-серверы: проверяем, что процесс стартует
check_cmd "openai-gpt-image-mcp" "$NODE_BIN/node" "/Users/alekseidoronin/Documents/CURSOR/openai-gpt-image-mcp/dist/index.js"
check_cmd "playwright" "$NODE_BIN/npx" "-y" "@playwright/mcp@latest"
check_cmd "postgres" "$NODE_BIN/npx" "-y" "@modelcontextprotocol/server-postgres" "postgresql://localhost/postgres"

export API_KEY="sk-user-c00JzcOBQsOfFeMhOgFz8KZ5NVjgj5Lq60XAjxLwl-Ke2m0OGRyRly8s-VLLbxrD5oBBlJRRyQAZEBbIvG6GZjAkzHBF3rG6tlMKCyTxFrVZDSpoV2dyPyQGRwkNbPX8sRA"
check_cmd "TestSprite" "$NODE_BIN/npx" "-y" "@testsprite/testsprite-mcp@latest"

log "--- end ---"
