.PHONY: install dev test test-unit test-integration lint format seed run clean help web

PYTHON ?= python3
GRAPH ?= repograph

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	$(PYTHON) -m pip install .

dev: ## Install with development dependencies
	$(PYTHON) -m pip install -e ".[dev]"

test: test-unit test-integration ## Run all tests

test-unit: ## Run unit tests
	$(PYTHON) -m pytest tests/unit/ -v --tb=short

test-integration: ## Run integration tests (requires FalkorDB)
	$(PYTHON) -m pytest tests/integration/ -v --tb=short -m integration

test-coverage: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ -v --cov=repograph --cov-report=term-missing --cov-report=html

lint: ## Run linter
	$(PYTHON) -m ruff check repograph/ tests/

format: ## Auto-format code
	$(PYTHON) -m ruff format repograph/ tests/
	$(PYTHON) -m ruff check --fix repograph/ tests/

seed: ## Load demo data into FalkorDB
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) seed

bus-factor: ## Show bus factor report
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) bus-factor

silos: ## Show knowledge silos
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) silos

risks: ## Show risk hotspots
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) risks

coupling: ## Show module coupling
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) coupling

summary: ## Show graph summary
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) summary

docker-up: ## Start FalkorDB and app with Docker Compose
	docker-compose up -d

docker-down: ## Stop Docker Compose services
	docker-compose down

web: ## Start the web dashboard (requires FalkorDB)
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) web

teams: ## Load team definitions from teams.yml
	$(PYTHON) -m repograph.cli.main --graph $(GRAPH) teams teams.yml

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
