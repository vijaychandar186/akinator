# https://github.com/casey/just

# Don't show the recipe name when running
set quiet

# Default DATABASE_URL — matches the docker-compose.yml credentials.
# Override by setting DATABASE_URL in your environment or a .env file.
export DATABASE_URL := env_var_or_default("DATABASE_URL", "postgresql://akinator:akinator@localhost:5432/akinator")

# Default recipe, it's run when just is invoked without a recipe
default:
  just --list --unsorted

# Sync dev dependencies
dev-sync:
    uv sync --all-extras --cache-dir .uv_cache

# Sync production dependencies (excludes dev dependencies)
prod-sync:
	uv sync --all-extras --no-dev --cache-dir .uv_cache

# Install pre commit hooks
install-hooks:
	uv run pre-commit install

# Run ruff formatting
format:
	uv run ruff format

# Run ruff linting and mypy type checking
lint:
	uv run ruff check --fix
	uv run mypy --ignore-missing-imports --install-types --non-interactive --package app

# Run tests using pytest
test:
	uv run pytest --verbose --color=yes tests

# Run all checks: format, lint, and test
validate: format lint test

# Build docker image
dockerize:
	docker build -t python-repo-template .

# Fetch famous people from Wikidata and seed the database
# Usage: just fetch [count] [min_sitelinks]
fetch count="2000" min_sitelinks="30":
    uv run python main.py fetch --count {{count}} --min-sitelinks {{min_sitelinks}}

# Fill enrichment columns (series, genre, award, hair, etc.) for existing characters,
# then regenerate questions and likelihoods — much faster than a full re-fetch.
# Usage: just fill [min_prevalence]
fill min_prevalence="0.01":
    uv run python main.py fill --min-prevalence {{min_prevalence}}

# Start a terminal game session
play:
    uv run python main.py play

# Batch-retrain likelihoods from saved game feedback
retrain:
    uv run python main.py retrain

# Start the FastAPI server (requires DATABASE_URL env var)
serve:
    uv run python main.py serve

# Start the server with the browser UI enabled at http://localhost:8000/ui
# Pass reload=true for auto-reload on code changes: just serve-ui reload=true
serve-ui reload="false":
    uv run python main.py serve --ui {{ if reload == "true" { "--reload" } else { "" } }}

# Run the batch retraining script directly as a module
retrain-module:
    uv run python -m app.learning
