.PHONY: dev dev-up dev-down dev-logs kill-all

# Start everything with live API logs in terminal
dev:
	@echo "=== Force killing ALL existing services ==="
	@pkill -9 -f "uvicorn.*ecom_arb" 2>/dev/null || true
	@pkill -9 -f "ngrok" 2>/dev/null || true
	@lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	@lsof -ti :3000 | xargs kill -9 2>/dev/null || true
	@lsof -ti :4040 | xargs kill -9 2>/dev/null || true
	@sleep 2
	@echo "=== Starting ngrok ==="
	@ngrok http 8000 --log=stdout > /tmp/ngrok.log 2>&1 &
	@echo "Waiting for ngrok..."
	@sleep 3
	@echo "=== Getting ngrok URL and updating .env ==="
	@NGROK_URL=$$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])") && \
		if grep -q "^WEBHOOK_BASE_URL=" .env 2>/dev/null; then \
			sed -i '' "s|^WEBHOOK_BASE_URL=.*|WEBHOOK_BASE_URL=$$NGROK_URL|" .env; \
		else \
			echo "WEBHOOK_BASE_URL=$$NGROK_URL" >> .env; \
		fi && \
		echo "ngrok: $$NGROK_URL" && \
		echo "WEBHOOK_BASE_URL set to: $$NGROK_URL"
	@echo "=== Starting frontend (background) ==="
	@cd frontend && npm run dev > /tmp/frontend.log 2>&1 &
	@echo "Frontend: http://localhost:3000"
	@echo ""
	@echo "=== Starting API (live logs below) ==="
	@echo "Press Ctrl+C to stop"
	@echo ""
	@sleep 1
	uvicorn src.ecom_arb.api.app:app --reload --port 8000

# Start all in background (no live logs)
dev-up:
	@./scripts/dev-up.sh

# Stop all services
dev-down:
	@./scripts/dev-down.sh

# Kill all dev processes
kill-all:
	@lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	@lsof -ti :3000 | xargs kill -9 2>/dev/null || true
	@lsof -ti :4040 | xargs kill -9 2>/dev/null || true
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
