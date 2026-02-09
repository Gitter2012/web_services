#!/usr/bin/env bash
# ResearchPulse Service Manager
# =============================
# Usage: ./run.sh {start|stop|status|restart|trigger}
#
# Configuration:
#   - Secrets (passwords, API keys): .env
#   - Non-sensitive defaults: /config/defaults.yaml, /apps/<app>/config/defaults.yaml
#   - Email addresses and SMTP profile host/user live in YAML defaults
#
# Runtime override examples (environment variables override YAML defaults):
#   LOG_LEVEL=DEBUG ./run.sh start
#   ARXIV_CATEGORIES=cs.AI,cs.NE ./run.sh start
#   ENABLED_APPS=arxiv_crawler,arxiv_ui ./run.sh start
#
# For permanent changes, edit:
#   - /config/defaults.yaml (project-level)
#   - /apps/<app>/config/defaults.yaml (app-level)

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$BASE_DIR/run"
PID_FILE="$PID_DIR/app.pid"
LOG_DIR="$BASE_DIR/logs"
LOG_FILE="${LOG_FILE:-$LOG_DIR/app.log}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
APP_MODULE="${APP_MODULE:-main:app}"
[ -x "/root/myenv/bin/python" ] && PYTHON_BIN="/root/myenv/bin/python" || PYTHON_BIN="python"

load_env() {
  if [ -f "$BASE_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$BASE_DIR/.env"
    set +a
  fi
}

start() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running (PID $(cat "$PID_FILE"))"
    return 0
  fi
  load_env
  nohup ${PYTHON_BIN} -m uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "Started (PID $(cat "$PID_FILE"))"
}

stop() {
  if [ ! -f "$PID_FILE" ]; then
    echo "Not running"
    return 0
  fi
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID"
    fi
    echo "Stopped"
  else
    echo "Stale PID file"
  fi
  rm -f "$PID_FILE"
}

status() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Running (PID $(cat "$PID_FILE"))"
  else
    echo "Not running"
  fi
}

trigger() {
  load_env
  url="http://${HOST}:${PORT}/arxiv/crawler/trigger"
  if command -v curl >/dev/null 2>&1; then
    curl -sS -X POST "$url"
  else
    ${PYTHON_BIN} - <<PY
import urllib.request

url = "http://${HOST}:${PORT}/arxiv/crawler/trigger"
req = urllib.request.Request(url, method="POST")
with urllib.request.urlopen(req) as resp:
    print(resp.read().decode("utf-8"))
PY
  fi
}

restart() {
  stop
  start
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  restart) restart ;;
  trigger) trigger ;;
  *)
    echo "Usage: $0 {start|stop|status|restart|trigger}"
    exit 1
    ;;
esac
