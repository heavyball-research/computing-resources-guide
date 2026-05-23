from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CONFIG_FILENAME = ".ccsync.toml"


@dataclass
class RemoteCfg:
    host: str
    path: str
    user: str | None = None
    port: int | None = None
    identity_file: str | None = None

    @property
    def ssh_target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    @property
    def ssh_opts(self) -> list[str]:
        opts: list[str] = []
        if self.port is not None:
            opts += ["-p", str(self.port)]
        if self.identity_file:
            opts += ["-i", self.identity_file]
        return opts

    def ssh_cmd(self, pty: bool = False) -> list[str]:
        cmd = ["ssh"]
        if pty:
            cmd.append("-t")
        cmd += self.ssh_opts
        cmd.append(self.ssh_target)
        return cmd

    def rsync_ssh_arg(self) -> str:
        parts = ["ssh"]
        if self.port is not None:
            parts += ["-p", str(self.port)]
        if self.identity_file:
            parts += ["-i", self.identity_file]
        return " ".join(parts)


@dataclass
class ComputeCfg:
    host: str
    path: str | None = None  # defaults to RemoteCfg.path (shared FS)
    user: str | None = None

    @property
    def ssh_target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host


@dataclass
class SyncCfg:
    exclude: list[str] = field(default_factory=list)
    debounce_ms: int = 500
    delete: bool = True
    log_pull_interval_s: int = 0  # 0 disables periodic log mirroring in `watch`


@dataclass
class PullCfg:
    paths: list[str] = field(default_factory=list)


@dataclass
class RunCfg:
    tmux_prefix: str = "ccs"
    log_dir: str = ".ccsync/logs"
    shell: str = "bash -lc"


@dataclass
class Config:
    project_root: Path
    remote: RemoteCfg
    sync: SyncCfg
    pull: PullCfg
    run: RunCfg
    compute: ComputeCfg | None = None

    @property
    def work_path(self) -> str:
        if self.compute and self.compute.path:
            return self.compute.path
        return self.remote.path


def find_config(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for d in (cur, *cur.parents):
        candidate = d / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No {CONFIG_FILENAME} found from {cur} up to /. Run `ccsync init`."
    )


def load_config(start: Path | None = None) -> Config:
    path = find_config(start)
    with path.open("rb") as f:
        raw = tomllib.load(f)

    if "remote" not in raw or "host" not in raw["remote"] or "path" not in raw["remote"]:
        raise ValueError(f"{path}: [remote] section requires host and path")

    r = raw["remote"]
    identity = r.get("identity_file")
    if identity:
        identity = str(Path(identity).expanduser())
    remote = RemoteCfg(
        host=r["host"],
        path=r["path"],
        user=r.get("user"),
        port=r.get("port"),
        identity_file=identity,
    )
    sync = SyncCfg(**raw.get("sync", {}))
    pull = PullCfg(**raw.get("pull", {}))
    run = RunCfg(**raw.get("run", {}))

    compute: ComputeCfg | None = None
    if "compute" in raw:
        c = raw["compute"]
        if "host" not in c:
            raise ValueError(f"{path}: [compute] section requires host")
        compute = ComputeCfg(host=c["host"], path=c.get("path"), user=c.get("user"))

    return Config(
        project_root=path.parent,
        remote=remote,
        sync=sync,
        pull=pull,
        run=run,
        compute=compute,
    )
