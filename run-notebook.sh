#!/usr/bin/env bash
# ============================================================
# Vigour POC — Launch Jupyter Lab as a background service
#
# Usage:
#   ./run-notebook.sh          # start
#   ./run-notebook.sh stop     # stop
#   ./run-notebook.sh status   # check if running
#   ./run-notebook.sh log      # tail the log
# ============================================================
set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJ_ROOT/.venv"
NOTEBOOK_DIR="$PROJ_ROOT/pipeline-poc/notebooks"
LOG_FILE="$PROJ_ROOT/.jupyter.log"
PID_FILE="$PROJ_ROOT/.jupyter.pid"
PORT="${JUPYTER_PORT:-8888}"

# Use RTX 3060 (GPU 0, sm_86) — RTX 5080 (GPU 1, sm_120) needs newer torch
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

_pid() {
    [ -f "$PID_FILE" ] && cat "$PID_FILE" || echo ""
}

_is_running() {
    local pid=$(_pid)
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

cmd_stop() {
    if _is_running; then
        local pid=$(_pid)
        echo "Stopping Jupyter (PID $pid)..."
        kill "$pid" 2>/dev/null || true
        # wait up to 5s for clean exit
        for _ in 1 2 3 4 5; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$PID_FILE"
        echo "Stopped."
    else
        echo "Not running."
        rm -f "$PID_FILE"
    fi
}

cmd_status() {
    if _is_running; then
        local pid=$(_pid)
        echo "Jupyter is running (PID $pid) on port $PORT"
        echo "  Local:  http://localhost:$PORT"
        echo "  Remote: http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PORT"
        echo "  Log:    $LOG_FILE"
    else
        echo "Jupyter is not running."
        rm -f "$PID_FILE"
    fi
}

cmd_log() {
    if [ -f "$LOG_FILE" ]; then
        tail -40 "$LOG_FILE"
    else
        echo "No log file yet."
    fi
}

cmd_start() {
    if _is_running; then
        echo "Already running (PID $(_pid))."
        cmd_status
        return 0
    fi

    if [ ! -d "$VENV_DIR" ]; then
        echo "Venv not found. Run ./install.sh first."
        exit 1
    fi

    echo "Starting Jupyter Lab on 0.0.0.0:$PORT ..."

    nohup "$VENV_DIR/bin/jupyter" lab \
        --ip=0.0.0.0 \
        --port="$PORT" \
        --no-browser \
        --notebook-dir="$NOTEBOOK_DIR" \
        --ServerApp.token='' \
        --ServerApp.password='' \
        --ServerApp.allow_origin='*' \
        --ServerApp.allow_remote_access=True \
        > "$LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"

    # Wait a moment for startup
    sleep 2

    if _is_running; then
        echo ""
        echo "Jupyter Lab is running (PID $pid)"
        echo ""
        echo "  Local:  http://localhost:$PORT"
        echo "  Remote: http://$(hostname -I 2>/dev/null | awk '{print $1}'):$PORT"
        echo ""
        echo "  Open 07_live_dashboard.ipynb for top-down tracking + metrics"
        echo ""
        echo "  ./run-notebook.sh stop    — shut down"
        echo "  ./run-notebook.sh log     — view output"
        echo "  ./run-notebook.sh status  — check"
    else
        echo "Failed to start. Check log:"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

case "${1:-start}" in
    start)  cmd_start  ;;
    stop)   cmd_stop   ;;
    status) cmd_status ;;
    log)    cmd_log    ;;
    restart)
        cmd_stop
        sleep 1
        cmd_start
        ;;
    *)
        echo "Usage: $0 {start|stop|status|log|restart}"
        exit 1
        ;;
esac
