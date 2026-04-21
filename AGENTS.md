# AGENTS.md — AI Coding Agent Reference

Essential information for AI coding agents working on this project.

---

## Project Overview

**python-uv-just-ruff-mypy-pytest-loguru-starter** is a production-ready Python 3.13 project template built with modern tooling.

| Tool | Role |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Package manager & virtual environments |
| [just](https://just.systems/) | Task runner |
| [ruff](https://docs.astral.sh/ruff/) | Linting & formatting |
| [mypy](https://mypy.readthedocs.io/) | Static type checking |
| [pytest](https://docs.pytest.org/) | Testing |
| [loguru](https://loguru.readthedocs.io/) | Logging |
| [pre-commit](https://pre-commit.com/) | Git hooks |

---

## Project Structure

```
app/                    # main package
  __init__.py
  core.py
tests/                  # pytest tests (mirror package structure)
  __init__.py
  test_core.py
main.py                 # CLI entrypoint
pyproject.toml          # project metadata & dependencies
ruff.toml               # ruff linting/formatting config
Justfile                # task runner recipes
Dockerfile              # multi-stage production image (uv builder + slim final)
.pre-commit-config.yaml # git hooks (ruff check + format)
.python-version         # 3.13
```

---

## Running Tests

Run all tests:

```bash
just test
```

Run a specific test file:

```bash
uv run pytest tests/test_core.py --verbose
```

Run a single test by name:

```bash
uv run pytest tests/test_core.py::test_name --verbose
```

After making changes, always run `just validate` to confirm format, lint, and tests all pass.

---

## Running Lints

```bash
just lint        # ruff check --fix + mypy
just format      # ruff format
just validate    # format + lint + test (what CI runs)
```

---

## Dependencies

Edit `pyproject.toml`:

```toml
[project]
dependencies = [
    "loguru>=0.7.3",   # prod deps here
]

[dependency-groups]
dev = [
    "pytest>=8.3.4",   # dev-only deps here
]
```

After editing, run `just dev-sync` to update the virtual environment.

---

## CI

GitHub Actions runs `just validate` on Python 3.13 on every push to `main`. Publishing to PyPI is triggered by a version tag (`v*.*.*`) and requires a `PYPI_TOKEN` secret.

---

## Docker

Multi-stage build:
1. **Builder** — `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`: installs prod deps into `/app/.venv`
2. **Final** — `python:3.13-slim-bookworm`: copies app + venv only, no uv or build tools

Requires `uv.lock`. Generate with `uv sync` before building.

---

## Development Guidelines

- **All changes must be tested.** If you didn't add or update a test, you're not done.
- **ALWAYS attempt to add a test case for changed behaviour**, even for small fixes.
- **PREFER integration tests** over unit tests where practical.
- **PREFER running specific tests** over the entire suite when iterating.
- **ALWAYS run `just validate` before declaring a task done** — it catches format, lint, and test failures.
- **NEVER call `pip` directly** — always `uv add`, `uv sync`, or `uv run`.
- **NEVER use `print` or stdlib `logging`** — use `from loguru import logger`.
- **NEVER use bare `except:`** — always catch a specific exception type.
- **NEVER assume ruff or mypy warnings are pre-existing** — treat all warnings as new.
- **PREFER `if x is not None:` and guard clauses** over nested conditionals.
- **PREFER top-level imports** — never import inside functions unless unavoidable.
- **AVOID shortening variable names** — use `version` not `ver`, `requires_python` not `rp`.
- **AVOID writing significant new code** when an existing utility or stdlib function would do.
- **Annotate all public functions and methods** — mypy enforces this in CI.
- **Use `# type: ignore[specific-code]`** not bare `# type: ignore` when suppressing mypy.
- **Use `# noqa: XXXX`** not bare `# noqa` when suppressing ruff.
- **Follow existing code style** — check neighbouring files for patterns before writing new ones.
- **Lock file**: `uv.lock` is gitignored in the template. When using this as a real project, remove the `uv.lock` line from `.gitignore` and commit the lock file.
