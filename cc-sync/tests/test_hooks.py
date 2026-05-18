import json
from pathlib import Path

from ccsync.hooks import HOOK_COMMAND, HOOK_MATCHER, install, uninstall


def test_install_creates_settings(tmp_path: Path):
    path = install(tmp_path)
    data = json.loads(path.read_text())
    entries = data["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == HOOK_MATCHER
    assert entries[0]["hooks"][0]["command"] == HOOK_COMMAND


def test_install_is_idempotent(tmp_path: Path):
    install(tmp_path)
    install(tmp_path)
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    cmds = [h["command"] for h in data["hooks"]["PostToolUse"][0]["hooks"]]
    assert cmds.count(HOOK_COMMAND) == 1


def test_install_preserves_other_hooks(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({
        "hooks": {"PostToolUse": [{
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "echo hi"}],
        }]}
    }))
    install(tmp_path)
    data = json.loads(settings.read_text())
    matchers = [e["matcher"] for e in data["hooks"]["PostToolUse"]]
    assert "Bash" in matchers
    assert HOOK_MATCHER in matchers


def test_uninstall_removes_only_our_hook(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({
        "hooks": {"PostToolUse": [{
            "matcher": HOOK_MATCHER,
            "hooks": [
                {"type": "command", "command": "echo other"},
                {"type": "command", "command": HOOK_COMMAND},
            ],
        }]}
    }))
    uninstall(tmp_path)
    data = json.loads(settings.read_text())
    cmds = [h["command"] for h in data["hooks"]["PostToolUse"][0]["hooks"]]
    assert HOOK_COMMAND not in cmds
    assert "echo other" in cmds
