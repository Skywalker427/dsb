.PHONY: help setup install migrate start stop restart status run test clean docker-build docker-run

help:
	@echo "Available commands:"
	@echo "  make setup      - Complete development setup"
	@echo "  make install    - Install dependencies"
	@echo "  make migrate    - Run database migrations"
	@echo ""
	@echo "Service control:"
	@echo "  make start      - Start both API and workers"
	@echo "  make stop       - Stop both API and workers"
	@echo "  make restart    - Restart both API and workers"
	@echo "  make status     - Show service status"
	@echo ""
	@echo "Individual services:"
	@echo "  make run        - Run application in development mode"
	@echo "  make workers    - Run background workers"
	@echo "  make dev        - Run both API and workers (in parallel)"
	@echo ""
	@echo "Development:"
	@echo "  make test       - Run all tests"
	@echo "  make test-unit  - Run unit tests only"
	@echo "  make test-e2e   - Run end-to-end tests"
	@echo "  make lint       - Run code linters"
	@echo "  make format     - Format code with black"
	@echo "  make clean      - Clean temporary files"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run - Run Docker container"

setup:
	@./scripts/setup_dev.sh

install:
	uv sync

migrate:
	@./scripts/init_db.sh

# Service control commands using the control script
start:
	@./scripts/control.sh start

stop:
	@./scripts/control.sh stop

restart:
	@./scripts/control.sh restart

status:
	@./scripts/control.sh status

# Individual service commands (legacy compatibility)
run:
	@./scripts/run_dev.sh

workers:
	@./scripts/run_workers.sh

dev:
	@echo "Starting API and Workers in parallel..."
	@./scripts/run_dev.sh & ./scripts/run_workers.sh

test:
	uv run pytest tests/ -v --cov=app --cov-report=html

test-unit:
	uv run pytest tests/unit/ -v

test-e2e:
	uv run pytest tests/e2e/ -v

lint:
	uv run ruff check app/ tests/
	uv run mypy app/

format:
	uv run black app/ tests/
	uv run ruff check app/ tests/ --fix

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage

docker-build:
	docker build -t dsb-backend:latest .

docker-run:
	docker run --env-file .env.docker -p 9000:9000 dsb-backend:latest