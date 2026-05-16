#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$ROOT/.bot.pid"
LOGFILE="$ROOT/bot.log"
VENV="$ROOT/.venv/bin/activate"

up() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Bot is already running (PID $(cat "$PIDFILE"))"
        return 1
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
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Bot stopped (PID $PID)"
    else
        echo "Bot process $PID not found, cleaning up stale PID file"
    fi
    rm -f "$PIDFILE"
}

status() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Bot is running (PID $(cat "$PIDFILE"))"
    else
        echo "Bot is not running"
        rm -f "$PIDFILE" 2>/dev/null
    fi
}

case "${1:-}" in
    up)   up ;;
    down)    down ;;
    restart) down 2>/dev/null; up ;;
    status)  status ;;
    *)       echo "Usage: $0 {up|down|restart|status}" ;;
esac
