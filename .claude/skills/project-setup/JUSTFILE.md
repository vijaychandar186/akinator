# Justfile Reference

This project uses `just` as its task runner. See `just-workflow` skill for full details.

## This Project's Justfile

```just
set quiet

default:
  just --list --unsorted

dev-sync:
    uv sync --all-extras --cache-dir .uv_cache

prod-sync:
    uv sync --all-extras --no-dev --cache-dir .uv_cache

install-hooks:
    uv run pre-commit install

format:
    uv run ruff format

lint:
    uv run ruff check --fix
    uv run mypy --ignore-missing-imports --install-types --non-interactive --package python_repo_template

test:
    uv run pytest --verbose --color=yes tests

validate: format lint test

dockerize:
    docker build -t python-repo-template .

run number:
    uv run main.py --number {{number}}
```

## Recipe Template

```just
# One-line description (shows in `just --list`)
recipe-name arg="default":
    uv run python -m my_module {{arg}}
```

Rules: tabs not spaces, `{{variable}}` for interpolation, `set quiet` suppresses recipe names.
