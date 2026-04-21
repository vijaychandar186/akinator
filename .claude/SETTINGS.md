# .claude/settings.json Reference

Full documentation for this project's Claude Code configuration.

---

## `defaultMode`

```json
"defaultMode": "bypassPermissions"
```

Skips the per-tool approval prompt. Claude can call any allowed tool without asking first.
Set to `"default"` to re-enable prompts (useful when working with untrusted agents).

---

## `permissions.allow`

Explicit allowlist of tools Claude can use without prompting. Every tool not in this list
requires user approval at runtime.

| Tool | Purpose |
|---|---|
| `Bash` | Run shell commands |
| `Read` / `Edit` / `Write` / `MultiEdit` | File operations |
| `Glob` / `Grep` | File search |
| `Agent` / `SendMessage` | Spawn and communicate with sub-agents |
| `WebFetch` / `WebSearch` | Fetch URLs and search the web |
| `TodoWrite` | Manage task lists |
| `Task*` | Create, list, update, stop tasks |
| `Cron*` | Schedule recurring jobs |
| `EnterPlanMode` / `ExitPlanMode` | Structured planning sessions |
| `EnterWorktree` / `ExitWorktree` | Git worktree isolation |
| `Skill` / `ToolSearch` | Load and invoke skills |
| `NotebookEdit` | Edit Jupyter notebooks |
| `LSP` | Language server queries (go-to-def, hover, etc.) |
| `RemoteTrigger` | Trigger remote Claude agents |
| `WorkFlow` | Multi-step workflow execution |

---

## `hooks`

Hooks run shell commands automatically in response to Claude's actions.

### `PostToolUse` — `Edit|Write|MultiEdit`

```json
"command": "uv run .claude/hooks/post-edit-format.py"
```

**Trigger**: After every file edit or write.
**What it does**: Auto-formats the edited file before Claude continues:
- `.py` / `.pyi` → `uvx ruff format`
- `.yaml` / `.yml` / `.json` → `npx prettier --write`

This means Claude always sees and works with already-formatted code, preventing
format-only diffs from accumulating.

**Script**: [hooks/post-edit-format.py](hooks/post-edit-format.py)

---

## Other Available Hook Events

Not used in this project but available if needed:

| Event | When it fires |
|---|---|
| `PreToolUse` | Before a tool is called — can block it |
| `PostToolUse` | After a tool completes |
| `SessionStart` | When a Claude Code session begins |
| `SessionEnd` | When a session ends |
| `Notification` | When Claude sends a notification |

### Example: block direct pip usage

```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "echo $CLAUDE_TOOL_INPUT | grep -q 'pip install' && exit 1 || exit 0"
      }
    ]
  }
]
```

---

## Adding a New Hook

1. Create a script in `.claude/hooks/`
2. Add an entry under the relevant event in `settings.json`
3. Use `uv run` for Python scripts (inline dependencies via PEP 723 `# /// script` headers)
4. Use `bash` for shell scripts
