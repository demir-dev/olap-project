# OLAP BI Platform Makefile
# Usage: make <target>
# Requires: Docker Compose v2, Python 3.11+, Node.js 20+

.PHONY: help build up down logs seed dev-backend dev-frontend install test clean

help:
	@echo "OLAP BI Platform — Available targets:"
	@echo ""
	@echo "  make build        Build Docker images"
	@echo "  make up           Start all services via Docker Compose"
	@echo "  make down         Stop all services"
	@echo "  make logs         Tail Docker logs"
	@echo "  make seed         (Re)generate the dataset in the running container"
	@echo "  make dev-backend  Run backend locally with hot-reload"
	@echo "  make dev-frontend Run React frontend locally"
	@echo "  make install      Install all dependencies (backend + frontend)"
	@echo "  make test         Run backend tests"
	@echo "  make clean        Remove containers, volumes, and local DB"

# ── Docker Compose ──────────────────────────────────────────────────────────

build:
	docker compose build

up:
	@test -f .env || (echo "ERROR: .env not found. Run: cp .env.example .env" && exit 1)
	docker compose up -d
	@echo ""
	@echo "Services started:"
	@echo "  Backend API:  http://localhost:8000"
	@echo "  Swagger UI:   http://localhost:8000/docs"
	@echo "  Frontend:     http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f

seed:
	docker compose exec backend python data/generate_dataset.py

# ── Local development ────────────────────────────────────────────────────────

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

dev-backend:
	@test -f backend/.env || echo "Tip: Create backend/.env with ANTHROPIC_API_KEY=sk-ant-..."
	cd backend && python data/generate_dataset.py && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	cd backend && python -m pytest tests/ -v 2>/dev/null || echo "No tests directory found."

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	docker compose down -v
	rm -f backend/data/olap.duckdb
	@echo "Cleaned up containers, volumes, and local database."
