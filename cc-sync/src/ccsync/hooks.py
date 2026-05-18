from __future__ import annotations

import json
from pathlib import Path

HOOK_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"
HOOK_COMMAND = "ccsync push --quiet"


def _settings_path(project_root: Path) -> Path:
    return project_root / ".claude" / "settings.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def install(project_root: Path) -> Path:
    path = _settings_path(project_root)
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("PostToolUse", [])

    for entry in entries:
        if entry.get("matcher") == HOOK_MATCHER:
            inner = entry.setdefault("hooks", [])
            if any(h.get("command") == HOOK_COMMAND for h in inner):
                return path
            inner.append({"type": "command", "command": HOOK_COMMAND})
            _save(path, data)
            return path

    entries.append({
        "matcher": HOOK_MATCHER,
        "hooks": [{"type": "command", "command": HOOK_COMMAND}],
    })
    _save(path, data)
    return path


def uninstall(project_root: Path) -> Path:
    path = _settings_path(project_root)
    if not path.exists():
        return path
    data = _load(path)
    entries = data.get("hooks", {}).get("PostToolUse", [])
    new_entries = []
    for entry in entries:
        inner = [h for h in entry.get("hooks", []) if h.get("command") != HOOK_COMMAND]
        if inner:
            entry["hooks"] = inner
            new_entries.append(entry)
    if "hooks" in data:
        if new_entries:
            data["hooks"]["PostToolUse"] = new_entries
        else:
            data["hooks"].pop("PostToolUse", None)
            if not data["hooks"]:
                data.pop("hooks")
    _save(path, data)
    return path
