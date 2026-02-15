# ===========================================
# ResearchPulse Makefile
# ===========================================
# Convenience commands for development and deployment

.PHONY: help install dev run test lint format clean docker-build docker-run docker-stop migrate backup

# ===========================================
# Default target
# ===========================================
help:
	@echo "ResearchPulse - Available Commands:"
	@echo ""
	@echo "  Development:"
	@echo "    make install        Install dependencies"
	@echo "    make dev            Install dev dependencies"
	@echo "    make run            Run development server"
	@echo "    make run-prod       Run production server"
	@echo ""
	@echo "  Testing & Quality:"
	@echo "    make test           Run all tests"
	@echo "    make test-cov       Run tests with coverage"
	@echo "    make lint           Run linter (ruff)"
	@echo "    make format         Format code (ruff)"
	@echo "    make typecheck      Run type checker (mypy)"
	@echo "    make pre-commit     Run all pre-commit hooks"
	@echo ""
	@echo "  Database:"
	@echo "    make migrate        Run database migrations"
	@echo "    make migrate-create Create a new migration"
	@echo "    make backup         Create database backup"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-build   Build Docker image"
	@echo "    make docker-run     Run Docker container"
	@echo "    make docker-stop    Stop Docker container"
	@echo "    make docker-logs    View Docker logs"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean          Remove build artifacts"
	@echo "    make clean-all      Remove all generated files"

# ===========================================
# Development
# ===========================================
install:
	pip install -r requirements.txt

dev:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov ruff mypy pre-commit

run:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

run-prod:
	uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# ===========================================
# Testing & Quality
# ===========================================
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=. --cov-report=html --cov-report=term

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy . --ignore-missing-imports

pre-commit:
	pre-commit run --all-files

# ===========================================
# Database
# ===========================================
migrate:
	alembic upgrade head

migrate-create:
	@read -p "Enter migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

backup:
	python -c "from apps.scheduler.jobs.backup import create_backup; import asyncio; asyncio.run(create_backup())"

# ===========================================
# Docker
# ===========================================
docker-build:
	docker build -t researchpulse:latest .

docker-run:
	docker run -d --name researchpulse \
		-p 8000:8000 \
		--env-file .env \
		-v $(PWD)/data:/app/data \
		-v $(PWD)/backups:/app/backups \
		researchpulse:latest

docker-stop:
	docker stop researchpulse && docker rm researchpulse

docker-logs:
	docker logs -f researchpulse

docker-compose-up:
	docker-compose up -d

docker-compose-down:
	docker-compose down

# ===========================================
# Milvus (Vector Database)
# ===========================================
milvus-up:
	docker-compose -f docker-compose.milvus.yml up -d

milvus-down:
	docker-compose -f docker-compose.milvus.yml down

# ===========================================
# Cleanup
# ===========================================
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml

clean-all: clean
	rm -rf .venv/ venv/ env/
	rm -rf dist/ build/
	rm -rf data/backups/*
