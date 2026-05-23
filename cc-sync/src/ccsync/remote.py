from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass

from .config import Config


def session_name(cfg: Config, name: str) -> str:
    return f"{cfg.run.tmux_prefix}-{name}"


LOG_SUBDIR = "logs/cc-sync"


def job_start_ts() -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S")


def remote_log_dir(cfg: Config, name: str) -> str:
    """Per-job log directory: <work_path>/logs/cc-sync/<name>/."""
    return f"{cfg.work_path.rstrip('/')}/{LOG_SUBDIR}/{name}"


def remote_log_path(cfg: Config, name: str, ts: str | None = None) -> str:
    """Path to a specific log; defaults to the per-job `latest.log` symlink."""
    base = remote_log_dir(cfg, name)
    return f"{base}/{ts}.log" if ts else f"{base}/latest.log"


def _wrap_for_compute(cfg: Config, workload: str) -> str:
    """If a compute node is configured, wrap workload so it runs there via ssh.

    The outer shell is always cfg.run.shell on the login (or sole) host. When
    [compute] is set, that outer shell ssh's into the compute node and runs
    cfg.run.shell again with the workload."""
    shell_cmd = f"{cfg.run.shell} {shlex.quote(workload)}"
    if cfg.compute is None:
        return shell_cmd
    return f"ssh -t {shlex.quote(cfg.compute.ssh_target)} {shlex.quote(shell_cmd)}"


def build_foreground_cmd(cfg: Config, user_cmd: list[str]) -> list[str]:
    workload = f"cd {shlex.quote(cfg.work_path)} && {shlex.join(user_cmd)}"
    return cfg.remote.ssh_cmd() + [_wrap_for_compute(cfg, workload)]


def build_launch_cmd(cfg: Config, name: str, user_cmd: list[str], ts: str | None = None) -> list[str]:
    sess = session_name(cfg, name)
    ts = ts or job_start_ts()
    log_dir = remote_log_dir(cfg, name)
    log = f"{log_dir}/{ts}.log"
    workload = (
        f"mkdir -p {shlex.quote(log_dir)} && "
        f"cd {shlex.quote(cfg.work_path)} && "
        f"ln -sfn {shlex.quote(ts + '.log')} {shlex.quote(log_dir + '/latest.log')} && "
        f"({shlex.join(user_cmd)}) 2>&1 | tee {shlex.quote(log)}; "
        f"echo CCSYNC_EXIT=$?"
    )
    tmux_payload = _wrap_for_compute(cfg, workload)
    tmux_cmd = f"tmux new-session -d -s {shlex.quote(sess)} {shlex.quote(tmux_payload)}"
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
    log = remote_log_path(cfg, name)  # latest.log symlink
    flag = "-F" if follow else ""  # -F (capital) survives symlink target swap
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
