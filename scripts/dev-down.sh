#!/bin/bash
# dev-down.sh - Stop all development services

echo "=== Stopping all services ==="

pkill -f "uvicorn.*ecom_arb" 2>/dev/null || true
pkill -f "next.*dev" 2>/dev/null || true
pkill -f "ngrok" 2>/dev/null || true

echo "All services stopped"
