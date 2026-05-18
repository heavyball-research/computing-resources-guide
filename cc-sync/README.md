# cc-sync

Edit locally, run remotely. A small Python CLI that mirrors your working tree
to a remote host via `rsync`, manages long-running jobs in `tmux`, and pulls
artifacts back when they finish. Plays well with Claude Code via an optional
`PostToolUse` hook that auto-syncs after every edit.

## Install

```bash
pip install -e .
```

## Quick start

```bash
cd my-project
ccsync init                       # writes .ccsync.toml
ccsync push                       # one-shot rsync to remote
ccsync watch                      # auto-sync on every save (Ctrl-C to stop)
ccsync run pytest -x              # sync + run foreground
ccsync launch train bash train.sh
ccsync logs train -f              # tail remote log; auto-pulls artifacts on exit
ccsync attach train               # jump into the tmux session
ccsync ps                         # list ccs-* sessions
ccsync install-hooks              # wire up Claude Code PostToolUse auto-sync
```

## Config (`.ccsync.toml`)

```toml
[remote]
host = "mybox"          # ~/.ssh/config alias
path = "/home/me/proj"

[sync]
exclude = [".git/", "__pycache__/", "target/", ".venv/"]
debounce_ms = 500
delete = true

[pull]
paths = ["logs/", "artifacts/", "outputs/"]

[run]
tmux_prefix = "ccs"
log_dir = ".ccsync/logs"
shell = "bash -lc"
```

## SSH

cc-sync assumes a working `~/.ssh/config` `Host` alias and a loaded ssh-agent.

## Scope

One remote per project; one-way sync (local → remote) plus opt-in artifact
pull. Not a multi-host fan-out tool, not a conflict resolver.
