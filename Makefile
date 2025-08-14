# Makefile for AI Persona Orchestrator

.PHONY: help test test-unit test-integration test-e2e test-coverage test-report dashboard clean

help:
	@echo "Available commands:"
	@echo "  make test          - Run all tests"
	@echo "  make test-unit     - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-e2e      - Run E2E tests only"
	@echo "  make test-coverage - Run tests with coverage report"
	@echo "  make test-report   - Generate HTML test reports"
	@echo "  make dashboard     - Start test dashboard server"
	@echo "  make clean         - Clean test artifacts"

# Activate virtual environment for all commands
VENV = source venv/bin/activate &&

test:
	$(VENV) pytest tests/ -v

test-unit:
	$(VENV) pytest tests/unit -v

test-integration:
	$(VENV) pytest tests/integration -v -m integration

test-e2e:
	$(VENV) pytest tests/e2e -v -m e2e

test-coverage:
	$(VENV) pytest tests/ --cov=backend --cov-report=term --cov-report=html -v

test-report:
	$(VENV) python scripts/run_tests_with_report.py

dashboard:
	@echo "Starting test dashboard at http://localhost:8080/test_dashboard/"
	@python scripts/test_dashboard_server.py

clean:
	@echo "Cleaning test artifacts..."
	@rm -rf .pytest_cache
	@rm -rf htmlcov
	@rm -rf test_reports
	@rm -f .coverage
	@rm -f coverage.xml
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "✨ Clean complete"

# Development helpers
install:
	python -m venv venv
	$(VENV) pip install -r backend/requirements.txt
	$(VENV) pip install pytest-html

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# Combined commands
test-all: test-report
	@echo "✅ All tests complete. Opening dashboard..."
	@make dashboard