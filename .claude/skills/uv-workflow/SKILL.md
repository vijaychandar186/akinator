# uv Workflow

## Core Commands for This Project

```bash
# Install all deps (prod + dev)
uv sync --all-extras

# Install prod deps only (no dev)
uv sync --no-dev --all-extras

# Add a prod dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Remove a dependency
uv remove <package>

# Run a command in the venv without activating it
uv run <command>

# Install exact versions from lock file
uv sync --frozen
```

## Lock File

`uv.lock` is gitignored in this template. When using it as a real project:
1. Remove the `uv.lock` line from `.gitignore`
2. Run `uv sync` to generate the lock file
3. Commit `uv.lock`

The Dockerfile requires `uv.lock` to exist (`--mount=type=bind,source=uv.lock`).

## Virtual Environment

uv automatically manages `.venv/` at the project root. The VS Code setting `python.defaultInterpreterPath` points to `.venv/bin/python`.

Never activate the venv manually — use `uv run` or let VS Code pick it up automatically.

## Exporting for pip Users

```bash
# With hashes (fully reproducible)
uv export > requirements.txt

# Without hashes (pip-friendly)
uv export --no-hashes > requirements.txt
```

## Python Version

Controlled by `.python-version` (currently `3.13`). uv reads this automatically.

## Publishing to PyPI

```bash
uv build
uv publish
```

CI publishes automatically on version tags (`v*.*.*`) via the `publish.yaml` workflow.
