from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from .config import Config


def session_name(cfg: Config, name: str) -> str:
    return f"{cfg.run.tmux_prefix}-{name}"


def remote_log_path(cfg: Config, name: str) -> str:
    return f"{cfg.remote.path.rstrip('/')}/.ccsync/{name}.log"


def build_foreground_cmd(cfg: Config, user_cmd: list[str]) -> list[str]:
    inner = f"cd {shlex.quote(cfg.remote.path)} && {shlex.join(user_cmd)}"
    return cfg.remote.ssh_cmd() + [f"{cfg.run.shell} {shlex.quote(inner)}"]


def build_launch_cmd(cfg: Config, name: str, user_cmd: list[str]) -> list[str]:
    sess = session_name(cfg, name)
    log = remote_log_path(cfg, name)
    inner = (
        f"mkdir -p {shlex.quote(cfg.remote.path.rstrip('/') + '/.ccsync')} && "
        f"cd {shlex.quote(cfg.remote.path)} && "
        f"({shlex.join(user_cmd)}) 2>&1 | tee {shlex.quote(log)}; "
        f"echo CCSYNC_EXIT=$?"
    )
    tmux_cmd = f"tmux new-session -d -s {shlex.quote(sess)} {shlex.quote(cfg.run.shell + ' ' + shlex.quote(inner))}"
    return cfg.remote.ssh_cmd() + [tmux_cmd]


def build_attach_cmd(cfg: Config, name: str) -> list[str]:
    sess = session_name(cfg, name)
    return cfg.remote.ssh_cmd(pty=True) + [f"tmux attach -t {shlex.quote(sess)}"]


def build_kill_cmd(cfg: Config, name: str) -> list[str]:
    sess = session_name(cfg, name)
    return cfg.remote.ssh_cmd() + [f"tmux kill-session -t {shlex.quote(sess)}"]


def build_list_cmd(cfg: Config) -> list[str]:
    prefix = cfg.run.tmux_prefix
    return cfg.remote.ssh_cmd() + [
        f"tmux ls 2>/dev/null | grep ^{shlex.quote(prefix)}- || true",
    ]


def build_tail_cmd(cfg: Config, name: str, follow: bool) -> list[str]:
    log = remote_log_path(cfg, name)
    flag = "-f" if follow else ""
    return cfg.remote.ssh_cmd() + [f"tail {flag} {shlex.quote(log)}".strip()]


@dataclass
class RunResult:
    returncode: int


def run_foreground(cfg: Config, user_cmd: list[str]) -> RunResult:
    cmd = build_foreground_cmd(cfg, user_cmd)
    proc = subprocess.run(cmd)
    return RunResult(returncode=proc.returncode)


def launch(cfg: Config, name: str, user_cmd: list[str]) -> RunResult:
    cmd = build_launch_cmd(cfg, name, user_cmd)
    proc = subprocess.run(cmd)
    return RunResult(returncode=proc.returncode)


def attach(cfg: Config, name: str) -> RunResult:
    cmd = build_attach_cmd(cfg, name)
    proc = subprocess.run(cmd)
    return RunResult(returncode=proc.returncode)


def kill(cfg: Config, name: str) -> RunResult:
    cmd = build_kill_cmd(cfg, name)
    proc = subprocess.run(cmd)
    return RunResult(returncode=proc.returncode)


def list_sessions(cfg: Config) -> str:
    cmd = build_list_cmd(cfg)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.stdout
