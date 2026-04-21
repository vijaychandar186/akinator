#!/bin/bash
set -e

# Install just (task runner) — devcontainer feature unavailable
mkdir -p "$HOME/.local/bin"
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"

uv sync --all-extras
uv run pre-commit install

bash .devcontainer/scripts/install-claude.sh
