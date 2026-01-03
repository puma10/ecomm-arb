#!/bin/bash
# dev-down.sh - Stop all development services

echo "=== Stopping all services ==="

for port in 8000 3000 4040; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Killing processes on port $port"
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
done

echo "All services stopped"
