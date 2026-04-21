# Just Workflow

[just](https://just.systems/) is the task runner for this project. It replaces Makefiles.

## All Recipes

```bash
just                  # list all recipes
just dev-sync         # uv sync --all-extras (install all deps)
just prod-sync        # uv sync --no-dev (prod only)
just install-hooks    # install pre-commit git hooks
just format           # ruff format
just lint             # ruff check --fix + mypy
just test             # pytest --verbose --color=yes
just validate         # format + lint + test (what CI runs)
just run <number>     # uv run main.py --number <number>
just dockerize        # docker build -t python-repo-template .
```

## Adding a New Recipe

Edit `Justfile`:

```just
# Description shown in `just --list`
my-recipe:
    uv run python -m my_module
```

Recipes use tabs (not spaces) for indentation.

## Key Behaviours

- `set quiet` — suppresses recipe names from output
- `default` recipe runs `just --list --unsorted` — always first
- All Python commands go through `uv run`, never raw `python`

## CI

The GitHub Actions validation action installs `just` via `extractions/setup-just@v2` and then runs `just validate`.
