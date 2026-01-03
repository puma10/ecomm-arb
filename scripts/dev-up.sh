#!/bin/bash
# dev-up.sh - Start all development services with ngrok

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Stopping existing services ==="

# Kill processes on our ports
for port in 8000 3000 4040; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Killing processes on port $port: $pids"
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
done

# Give processes time to die
sleep 1

echo "=== Starting ngrok ==="
ngrok http 8000 --log=stdout > /tmp/ngrok.log 2>&1 &
NGROK_PID=$!
echo "ngrok started (PID: $NGROK_PID)"

# Wait for ngrok to be ready
echo "Waiting for ngrok..."
for i in {1..30}; do
    if curl -s http://localhost:4040/api/tunnels > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Get the ngrok URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null)

if [ -z "$NGROK_URL" ]; then
    echo "ERROR: Failed to get ngrok URL"
    exit 1
fi

echo "ngrok URL: $NGROK_URL"

echo "=== Updating .env ==="
# Update or add WEBHOOK_BASE_URL in .env
if grep -q "^WEBHOOK_BASE_URL=" .env 2>/dev/null; then
    # macOS sed requires empty string for -i
    sed -i '' "s|^WEBHOOK_BASE_URL=.*|WEBHOOK_BASE_URL=$NGROK_URL|" .env
else
    echo "WEBHOOK_BASE_URL=$NGROK_URL" >> .env
fi
echo "Set WEBHOOK_BASE_URL=$NGROK_URL"

echo "=== Starting API server ==="
source .venv/bin/activate 2>/dev/null || true
uvicorn src.ecom_arb.api.app:app --reload --port 8000 > /tmp/api.log 2>&1 &
API_PID=$!
echo "API server started (PID: $API_PID)"

# Wait for API to be ready
echo "Waiting for API..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

echo "=== Starting frontend ==="
cd frontend
npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID)"
cd ..

echo ""
echo "=== All services started ==="
echo "  API:      http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  ngrok:    $NGROK_URL"
echo "  ngrok UI: http://localhost:4040"
echo ""
echo "Logs:"
echo "  tail -f /tmp/api.log"
echo "  tail -f /tmp/frontend.log"
echo "  tail -f /tmp/ngrok.log"
echo ""
echo "To stop all: ./scripts/dev-down.sh"
