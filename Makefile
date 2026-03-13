.PHONY: dev dev-up dev-down dev-logs kill-all

# Ngrok port (not managed by portless)
NGROK_PORT ?= 4040

# Start everything with live API logs in terminal
# Portless assigns ephemeral ports — no conflicts, no kill -9
dev:
	@echo "=== Starting services via portless ==="
	@echo "=== Starting API (background for ngrok setup) ==="
	@portless api.ecomm sh -c 'uvicorn src.ecom_arb.api.app:app --reload --host 0.0.0.0 --port $$PORT' > /tmp/api.log 2>&1 &
	@sleep 2
	@echo "API: https://api.ecomm.localhost:1355"
	@echo "=== Starting ngrok ==="
	@ngrok http https://api.ecomm.localhost:1355 --log=stdout > /tmp/ngrok.log 2>&1 &
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
	@cd frontend && portless ecomm npm run dev > /tmp/frontend.log 2>&1 &
	@echo "Frontend: https://ecomm.localhost:1355"
	@echo ""
	@echo "=== All services running ==="
	@echo "  API:      https://api.ecomm.localhost:1355"
	@echo "  Frontend: https://ecomm.localhost:1355"
	@echo "  Logs:     make dev-logs"
	@echo ""
	@echo "Press Ctrl+C or 'make dev-down' to stop"
	@wait

# Start all in background (no live logs)
dev-up:
	@./scripts/dev-up.sh

# Stop all services
dev-down:
	@./scripts/dev-down.sh

# Kill all dev processes
kill-all:
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
