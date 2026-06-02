from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .config import Config


def _with_slash(p: str) -> str:
    return p if p.endswith("/") else p + "/"


def build_push_cmd(cfg: Config, dry_run: bool = False) -> list[str]:
    cmd = ["rsync", "-avh"]
    if cfg.sync.delete:
        cmd.append("--delete")
    if dry_run:
        cmd.append("--dry-run")
    for pat in cfg.sync.exclude:
        cmd.append(f"--exclude={pat}")
    cmd += ["-e", cfg.remote.rsync_ssh_arg()]
    local = _with_slash(str(cfg.project_root))
    remote = f"{cfg.remote.ssh_target}:{_with_slash(cfg.remote.path)}"
    cmd += [local, remote]
    return cmd


def build_pull_cmd(cfg: Config, paths: list[str] | None = None) -> list[list[str]]:
    targets = paths if paths else cfg.pull.paths
    cmds: list[list[str]] = []
    for rel in targets:
        rel_slash = _with_slash(rel)
        remote = f"{cfg.remote.ssh_target}:{_with_slash(cfg.remote.path)}{rel_slash}"
        local_dest = cfg.project_root / rel
        local_dest.mkdir(parents=True, exist_ok=True)
        cmds.append([
            "rsync", "-avh", "-e", cfg.remote.rsync_ssh_arg(),
            remote, _with_slash(str(local_dest)),
        ])
    return cmds


def push(cfg: Config, dry_run: bool = False, quiet: bool = False) -> int:
    cmd = build_push_cmd(cfg, dry_run=dry_run)
    stdout = subprocess.DEVNULL if quiet else None
    proc = subprocess.run(cmd, stdout=stdout)
    return proc.returncode


def ensure_remote_log_dir(cfg: Config, quiet: bool = True) -> int:
    """`mkdir -p` the remote logs/cc-sync/ dir so the mirror has a source.

    The watcher mirrors logs from the remote every interval; if no job has been
    launched yet the remote dir doesn't exist and rsync's sender aborts with
    "change_dir ... failed: No such file or directory" (exit 23). Creating it
    up front makes the mirror a no-op rather than an error on a fresh host.
    """
    from .remote import LOG_SUBDIR
    remote_dir = cfg.work_path.rstrip("/") + "/" + LOG_SUBDIR
    cmd = cfg.remote.ssh_cmd() + [f"mkdir -p {shlex.quote(remote_dir)}"]
    stdout = subprocess.DEVNULL if quiet else None
    proc = subprocess.run(cmd, stdout=stdout)
    return proc.returncode


def build_logs_mirror_cmd(cfg: Config) -> list[str]:
    """rsync remote logs/cc-sync/ → local logs/cc-sync/ (same relative path)."""
    from .remote import LOG_SUBDIR
    remote = f"{cfg.remote.ssh_target}:{_with_slash(cfg.work_path.rstrip('/') + '/' + LOG_SUBDIR)}"
    local = cfg.project_root / LOG_SUBDIR
    local.mkdir(parents=True, exist_ok=True)
    return [
        "rsync", "-avh", "-e", cfg.remote.rsync_ssh_arg(),
        "--include=*.log", "--include=*/", "--exclude=*",
        remote, _with_slash(str(local)),
    ]


def mirror_logs(cfg: Config, quiet: bool = True) -> int:
    cmd = build_logs_mirror_cmd(cfg)
    stdout = subprocess.DEVNULL if quiet else None
    proc = subprocess.run(cmd, stdout=stdout)
    return proc.returncode


def pull(cfg: Config, paths: list[str] | None = None, quiet: bool = False) -> int:
    cmds = build_pull_cmd(cfg, paths)
    if not cmds:
        return 0
    stdout = subprocess.DEVNULL if quiet else None
    rc = 0
    for cmd in cmds:
        proc = subprocess.run(cmd, stdout=stdout)
        if proc.returncode != 0:
            rc = proc.returncode
    return rc
