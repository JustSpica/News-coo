#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$ROOT/.bot.pid"
LOGFILE="$ROOT/bot.log"
VENV="$ROOT/.venv/bin/activate"

valid_pid() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

running_pid() {
    valid_pid "$1" && kill -0 "$1" 2>/dev/null
}

up() {
    if [ -f "$PIDFILE" ]; then
        PID="$(cat "$PIDFILE")"
        if running_pid "$PID"; then
            echo "Bot is already running (PID $PID)"
            return 1
        fi
        echo "Cleaning up stale or invalid PID file"
        rm -f "$PIDFILE"
    fi

    source "$VENV"
    nohup python -m bot.main >> "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "Bot started (PID $!), logging to $LOGFILE"
}

down() {
    if [ ! -f "$PIDFILE" ]; then
        echo "Bot is not running (no PID file)"
        return 1
    fi

    PID="$(cat "$PIDFILE")"
    if ! valid_pid "$PID"; then
        echo "Invalid PID file, cleaning up"
    elif running_pid "$PID"; then
        kill "$PID"
        echo "Bot stopped (PID $PID)"
    else
        echo "Bot process $PID not found, cleaning up stale PID file"
    fi
    rm -f "$PIDFILE"
}

status() {
    if [ -f "$PIDFILE" ]; then
        PID="$(cat "$PIDFILE")"
        if running_pid "$PID"; then
            echo "Bot is running (PID $PID)"
            return
        fi
        rm -f "$PIDFILE" 2>/dev/null
    fi
    echo "Bot is not running"
}

case "${1:-}" in
    up)   up ;;
    down)    down ;;
    restart) down 2>/dev/null || true; up ;;
    status)  status ;;
    *)       echo "Usage: $0 {up|down|restart|status}" ;;
esac
