---
name: packaging
description: Packages and distributes Python libraries using pyproject.toml, uv build/publish, hatchling build backend, and GitHub Actions trusted publishing. Use when packaging for PyPI, publishing releases, or troubleshooting packaging issues.
---

# Python Library Packaging

## pyproject.toml for This Project

```toml
[project]
name = "my-package"
version = "0.1.0"
description = "Short description"
readme = "README.md"
license = { text = "MIT" }
authors = [{ name = "Name", email = "email@example.com" }]
requires-python = ">=3.13"
dependencies = [
    "loguru>=0.7.3",
]

[dependency-groups]
dev = [
    "mypy>=1.15.0",
    "pre-commit>=4.1.0",
    "pytest>=8.3.4",
    "ruff>=0.9.5",
]

[project.urls]
Homepage = "https://github.com/user/repo"
Repository = "https://github.com/user/repo"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Building and Publishing with uv

```bash
# Build sdist + wheel into dist/
uv build

# Publish to PyPI
uv publish

# Publish to TestPyPI
uv publish --index testpypi
```

Never use `pip install build` + `twine` — this project uses `uv build` and `uv publish`.

## GitHub Actions — Trusted Publishing

This project's `publish.yaml` triggers on `v*.*.*` tags:

```yaml
on:
  push:
    tags:
      - "v[0-9]+.[0-9]+.[0-9]+"

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: just validate
      - run: uv build && uv publish
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.PYPI_TOKEN }}
```

## Dependency Best Practices

- Minimum versions only: `loguru>=0.7.3` — never `loguru==0.7.3`
- Prod deps in `[project].dependencies`, dev in `[dependency-groups].dev`
- Dev deps never appear in the published package (`uv sync --no-dev` for prod)

## Entry Points (CLI)

```toml
[project.scripts]
my-cli = "my_package.cli:main"
```

## Lock File

`uv.lock` must be committed for real projects (remove it from `.gitignore`). The Dockerfile depends on it.

## Checklist

- [ ] `name`, `version`, `description`, `readme`, `license` set
- [ ] `requires-python = ">=3.13"`
- [ ] `authors` and `[project.urls]` filled in
- [ ] `LICENSE` file present
- [ ] `uv.lock` committed (removed from `.gitignore`)
- [ ] `uv build` succeeds locally
- [ ] `PYPI_TOKEN` secret set in GitHub repo settings
