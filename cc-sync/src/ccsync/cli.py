from __future__ import annotations

import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from . import hooks as hooks_mod
from . import remote as remote_mod
from . import sync as sync_mod
from .config import CONFIG_FILENAME, Config, load_config
from .watch import run_watcher

app = typer.Typer(add_completion=False, help="Local-edit / remote-run sync tool")
console = Console()


def _cfg() -> Config:
    try:
        return load_config()
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(2)


@app.command()
def init(
    host: Optional[str] = typer.Option(None, help="SSH host (alias or hostname)"),
    path: Optional[str] = typer.Option(None, help="Remote project path"),
    user: Optional[str] = typer.Option(None, help="SSH user (omit to use ~/.ssh/config)"),
    port: Optional[int] = typer.Option(None, help="SSH port"),
    identity_file: Optional[str] = typer.Option(None, help="Path to SSH private key"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
):
    """Scaffold .ccsync.toml in the current directory."""
    dest = Path.cwd() / CONFIG_FILENAME
    if dest.exists() and not force:
        console.print(f"[yellow]{dest} exists. Use --force to overwrite.[/]")
        raise typer.Exit(1)
    host = host or typer.prompt("Remote SSH host (alias or hostname)")
    path = path or typer.prompt("Remote project path")
    tmpl = resources.files("ccsync.templates").joinpath("ccsync.toml.tmpl").read_text()
    rendered = tmpl.format(host=host, path=path)
    extras: list[str] = []
    if user:
        extras.append(f'user = "{user}"')
    if port is not None:
        extras.append(f"port = {port}")
    if identity_file:
        extras.append(f'identity_file = "{identity_file}"')
    if extras:
        # Activate the optional block by replacing the commented hints.
        rendered = rendered.replace(
            '# Optional — set these if `~/.ssh/config` doesn\'t already resolve them.\n'
            '# user = "ubuntu"\n'
            '# port = 22\n'
            '# identity_file = "~/.ssh/id_ed25519"',
            "\n".join(extras),
        )
    dest.write_text(rendered)
    console.print(f"[green]wrote[/] {dest}")


@app.command()
def push(
    dry_run: bool = typer.Option(False, "--dry-run"),
    quiet: bool = typer.Option(False, "--quiet"),
):
    """Sync local → remote (rsync)."""
    cfg = _cfg()
    rc = sync_mod.push(cfg, dry_run=dry_run, quiet=quiet)
    if rc != 0 and not quiet:
        console.print(f"[red]rsync exited {rc}[/]")
    raise typer.Exit(rc)


@app.command()
def pull(
    paths: list[str] = typer.Argument(None, help="Override [pull].paths"),
    quiet: bool = typer.Option(False, "--quiet"),
):
    """Sync remote → local for configured paths."""
    cfg = _cfg()
    rc = sync_mod.pull(cfg, paths=paths or None, quiet=quiet)
    raise typer.Exit(rc)


@app.command()
def watch():
    """Watch local files; auto-sync on change."""
    cfg = _cfg()
    run_watcher(cfg)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(ctx: typer.Context):
    """Push, then ssh foreground to run a command and stream output."""
    cfg = _cfg()
    user_cmd = list(ctx.args)
    if not user_cmd:
        console.print("[red]usage: ccsync run <cmd> [args...][/]")
        raise typer.Exit(2)
    rc = sync_mod.push(cfg, quiet=True)
    if rc != 0:
        console.print(f"[red]push failed ({rc}); aborting[/]")
        raise typer.Exit(rc)
    res = remote_mod.run_foreground(cfg, user_cmd)
    raise typer.Exit(res.returncode)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def launch(ctx: typer.Context, name: str = typer.Argument(...)):
    """Push, then start a detached tmux job named ccs-<name>."""
    cfg = _cfg()
    user_cmd = list(ctx.args)
    if not user_cmd:
        console.print("[red]usage: ccsync launch <name> <cmd> [args...][/]")
        raise typer.Exit(2)
    rc = sync_mod.push(cfg, quiet=True)
    if rc != 0:
        console.print(f"[red]push failed ({rc}); aborting[/]")
        raise typer.Exit(rc)
    res = remote_mod.launch(cfg, name, user_cmd)
    if res.returncode == 0:
        console.print(f"[green]launched[/] {cfg.run.tmux_prefix}-{name}")
        console.print(f"  attach: ccsync attach {name}")
        console.print(f"  logs:   ccsync logs {name} -f")
    raise typer.Exit(res.returncode)


@app.command()
def attach(name: str):
    """Attach to the tmux session for <name>."""
    cfg = _cfg()
    res = remote_mod.attach(cfg, name)
    raise typer.Exit(res.returncode)


@app.command()
def logs(
    name: str,
    follow: bool = typer.Option(False, "-f", "--follow"),
    no_pull: bool = typer.Option(False, "--no-pull", help="Skip auto-pull on completion"),
):
    """Tail the remote log for <name>. With -f, auto-pulls artifacts on exit."""
    cfg = _cfg()
    cmd = remote_mod.build_tail_cmd(cfg, name, follow=follow)
    if not follow:
        proc = subprocess.run(cmd)
        raise typer.Exit(proc.returncode)
    saw_exit = False
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if "CCSYNC_EXIT=" in line:
                saw_exit = True
                break
        proc.terminate()
    except KeyboardInterrupt:
        pass
    if saw_exit and not no_pull:
        console.print("[cyan]job finished; pulling artifacts[/]")
        sync_mod.pull(cfg)


@app.command("logs-pull")
def logs_pull(name: str):
    """Snapshot remote logs/cc-sync/<name>/ to the same local path."""
    cfg = _cfg()
    remote_dir = remote_mod.remote_log_dir(cfg, name)
    dest = cfg.project_root / remote_mod.LOG_SUBDIR / name
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync", "-avh", "-L",  # -L deref the latest.log symlink to a file
        "-e", cfg.remote.rsync_ssh_arg(),
        f"{cfg.remote.ssh_target}:{remote_dir}/",
        f"{dest}/",
    ]
    proc = subprocess.run(cmd)
    if proc.returncode == 0:
        console.print(f"[green]pulled[/] {dest}/")
    raise typer.Exit(proc.returncode)


@app.command("ps")
def ps_cmd():
    """List ccs-* tmux sessions on the remote."""
    cfg = _cfg()
    out = remote_mod.list_sessions(cfg)
    sys.stdout.write(out)


@app.command()
def kill(name: str):
    """Kill the tmux session for <name>."""
    cfg = _cfg()
    res = remote_mod.kill(cfg, name)
    raise typer.Exit(res.returncode)


@app.command("install-hooks")
def install_hooks():
    """Install Claude Code PostToolUse hook that auto-syncs."""
    cfg = _cfg()
    path = hooks_mod.install(cfg.project_root)
    console.print(f"[green]installed[/] hook in {path}")


@app.command("uninstall-hooks")
def uninstall_hooks():
    """Remove the cc-sync PostToolUse hook."""
    cfg = _cfg()
    path = hooks_mod.uninstall(cfg.project_root)
    console.print(f"[green]removed[/] hook from {path}")


if __name__ == "__main__":
    app()
