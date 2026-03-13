.PHONY: dev dev-up dev-down dev-logs kill-all

# Port configuration — portless assigns ephemeral ports via $PORT
# These are only used as fallbacks when portless is not running
BACKEND_PORT ?= 8000
PORT ?= 3000
NGROK_PORT ?= 4040

# Start everything with live API logs in terminal
dev:
	@echo "=== Starting services via portless ==="
	@echo "=== Starting ngrok ==="
	@ngrok http $(BACKEND_PORT) --log=stdout > /tmp/ngrok.log 2>&1 &
	@echo "Waiting for ngrok..."
	@sleep 3
	@echo "=== Getting ngrok URL and updating .env ==="
	@NGROK_URL=$$(curl -s http://localhost:$(NGROK_PORT)/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])") && \
		if grep -q "^WEBHOOK_BASE_URL=" .env 2>/dev/null; then \
			sed -i '' "s|^WEBHOOK_BASE_URL=.*|WEBHOOK_BASE_URL=$$NGROK_URL|" .env; \
		else \
			echo "WEBHOOK_BASE_URL=$$NGROK_URL" >> .env; \
		fi && \
		echo "ngrok: $$NGROK_URL" && \
		echo "WEBHOOK_BASE_URL set to: $$NGROK_URL"
	@echo "=== Starting frontend ==="
	@cd frontend && portless ecomm -- npm run dev > /tmp/frontend.log 2>&1 &
	@echo "Frontend: https://ecomm.localhost"
	@echo ""
	@echo "=== Starting API (live logs below) ==="
	@echo "Press Ctrl+C to stop"
	@echo ""
	@sleep 1
	portless api.ecomm -- uvicorn src.ecom_arb.api.app:app --reload --host 0.0.0.0

# Start all in background (no live logs)
dev-up:
	@./scripts/dev-up.sh

# Stop all services
dev-down:
	@./scripts/dev-down.sh

# Kill all dev processes
kill-all:
	@pkill -f "portless.*ecomm" 2>/dev/null || true
	@pkill -f "uvicorn.*ecom_arb" 2>/dev/null || true
	@pkill -f "next.*dev" 2>/dev/null || true
	@pkill -f "ngrok" 2>/dev/null || true
	@echo "All services killed"

# Tail all logs
dev-logs:
	@tail -f /tmp/api.log /tmp/frontend.log /tmp/ngrok.log

# Run tests
test:
	python -m pytest tests/ -v

# Run linter
lint:
	ruff check src/ tests/

# Format code
format:
	ruff format src/ tests/
