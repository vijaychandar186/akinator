# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

"""Post-edit hook: auto-format Python and YAML/JSON files after Claude edits."""

import json
import os
import subprocess
import sys
from pathlib import Path


def format_python(file_path: str, cwd: str) -> None:
    subprocess.run(
        ["uvx", "ruff", "format", file_path],
        cwd=cwd,
        capture_output=True,
    )


def format_prettier(file_path: str, cwd: str) -> None:
    subprocess.run(
        ["npx", "--yes", "prettier", "--write", file_path],
        cwd=cwd,
        capture_output=True,
    )


def main() -> None:
    input_data = json.load(sys.stdin)

    tool_name = input_data.get("tool_name")
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path")

    if tool_name not in ("Write", "Edit", "MultiEdit") or not file_path:
        return

    cwd = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    ext = Path(file_path).suffix

    if ext in (".py", ".pyi"):
        format_python(file_path, cwd)
    elif ext in (".yaml", ".yml", ".json"):
        format_prettier(file_path, cwd)


if __name__ == "__main__":
    main()
