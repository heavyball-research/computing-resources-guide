"""modal-ssh CLI — launch / list / ssh / stop Modal GPU dev VMs.

Subcommands:
    modal-ssh up [config] [--gpu B200:2] [--duration 4]
    modal-ssh down [config]
    modal-ssh ls
    modal-ssh ssh [config]
    modal-ssh configs

`config` is a short name like `sglang` (→ configs/sglang.yml), a filename
like `sglang.yml`, or a full path. Omit to use `configs/default.yml`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CONFIGS_DIR = ROOT / "configs"
APP_FILE = str(ROOT / "modal_ssh.py")
MODAL_TOML = Path.home() / ".modal.toml"

_INSTANCE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_PROFILE_SECTION_RE = re.compile(r"^\[([^\]]+)\]", re.M)


def _validate_instance(s: str | None) -> str | None:
    """Empty/None → no instance. Otherwise must be alphanumeric / dash / underscore."""
    if not s:
        return None
    if not _INSTANCE_RE.match(s):
        sys.exit(f"invalid --instance value: {s!r} (use alphanumerics, dashes, underscores)")
    return s


def _apply_profile(profile: str | None) -> None:
    """Set MODAL_PROFILE so downstream `modal` subprocess/exec calls use it.
    No-op if profile is None (modal then falls back to whichever profile has
    active=true in ~/.modal.toml)."""
    if not profile:
        return
    if not MODAL_TOML.is_file():
        sys.exit(f"~/.modal.toml not found — run `modal setup` first")
    profiles = _PROFILE_SECTION_RE.findall(MODAL_TOML.read_text())
    if profile not in profiles:
        avail = ", ".join(profiles) or "(none)"
        sys.exit(f"profile {profile!r} not found in ~/.modal.toml. Available: {avail}")
    os.environ["MODAL_PROFILE"] = profile


def _apply_instance(name: str, instance: str | None) -> str:
    return f"{name}-{instance}" if instance else name


def _resolve_cfg(name: str | None) -> Path:
    """Accept short name (`sglang`), filename (`sglang.yml`), or full path."""
    if not name:
        return CONFIGS_DIR / "default.yml"
    p = Path(name)
    if p.is_file():
        return p
    for cand in (CONFIGS_DIR / name, CONFIGS_DIR / f"{name}.yml"):
        if cand.is_file():
            return cand
    sys.exit(f"config not found: {name}")


def _load(cfg_path: Path) -> dict:
    return yaml.safe_load(cfg_path.read_text()) or {}


# ── Subcommands ──────────────────────────────────────────────────────────

def cmd_up(args: argparse.Namespace) -> None:
    cfg_path = _resolve_cfg(args.config)
    env = {**os.environ, "CONFIG": str(cfg_path)}
    if args.gpu:
        env["MODAL_SSH_GPU"] = args.gpu
    if args.duration:
        env["MODAL_SSH_DURATION"] = str(args.duration)
    inst = _validate_instance(args.instance)
    if inst:
        env["MODAL_SSH_INSTANCE"] = inst
    tag = f" (instance={inst})" if inst else ""
    print(f"→ launching {cfg_path.name}{tag}")
    # exec so the user's terminal becomes the modal-run terminal directly.
    os.execvpe("modal", ["modal", "run", "--detach", APP_FILE], env)


def cmd_run(args: argparse.Namespace) -> None:
    """Submit a bash script as a Modal background job. Shares image / yml
    with `up`, but the container runs the script instead of sshd."""
    cfg_path = _resolve_cfg(args.config)
    script_path = Path(args.script).expanduser().resolve()
    if not script_path.is_file():
        sys.exit(f"script not found: {script_path}")

    env = {
        **os.environ,
        "CONFIG": str(cfg_path),
        "MODAL_SSH_MODE": "job",
        "MODAL_SSH_SCRIPT": str(script_path),
    }
    if args.gpu:
        env["MODAL_SSH_GPU"] = args.gpu
    if args.duration:
        env["MODAL_SSH_DURATION"] = str(args.duration)
    inst = _validate_instance(args.instance)
    if inst:
        env["MODAL_SSH_INSTANCE"] = inst

    cmd = ["modal", "run"]
    if not args.foreground:
        cmd.append("--detach")
    cmd.append(APP_FILE)

    tag = f" instance={inst}" if inst else ""
    mode = "foreground" if args.foreground else "detached"
    print(f"→ submitting job `{script_path.name}` on {cfg_path.name}{tag} ({mode})")
    os.execvpe("modal", cmd, env)


def cmd_logs(args: argparse.Namespace) -> None:
    """Tail / replay logs of a modal-ssh-managed app."""
    cfg = _load(_resolve_cfg(args.config))
    base_app = cfg.get("app_name")
    if not base_app:
        sys.exit("config has no app_name field")
    inst = _validate_instance(args.instance)
    target_name = _apply_instance(base_app, inst)

    # Pick newest live (or recent) app with that name.
    matches = [a for a in _list_apps() if _app_name(a) == target_name]
    if not matches:
        sys.exit(f"no app named {target_name} — has it ever been started?")
    # modal app list seems to return newest-first; take the first.
    appid = _app_id(matches[0])
    print(f"→ modal app logs {appid} ({target_name})")
    os.execvp("modal", ["modal", "app", "logs", appid])


def _list_apps() -> list[dict]:
    try:
        out = subprocess.run(
            ["modal", "app", "list", "--json"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        sys.exit(f"modal app list failed: {e.stderr or e}")
    return json.loads(out)


def _app_id(a: dict) -> str:
    return a.get("App ID") or a.get("AppID") or a.get("id") or ""


def _app_name(a: dict) -> str:
    return a.get("Description") or a.get("Name") or a.get("name") or ""


def _app_state(a: dict) -> str:
    return (a.get("State") or a.get("state") or "").lower()


def _is_live(state: str) -> bool:
    return not ("stop" in state or "terminated" in state or state == "done")


def cmd_down(args: argparse.Namespace) -> None:
    cfg = _load(_resolve_cfg(args.config))
    base_app = cfg.get("app_name")
    if not base_app:
        sys.exit("config has no app_name field")
    inst = _validate_instance(args.instance)
    if args.all and inst:
        sys.exit("--all and --instance are mutually exclusive")

    if args.all:
        # Match the bare base_app AND every `<base>-<suffix>` instance.
        def match(n: str) -> bool:
            return n == base_app or n.startswith(f"{base_app}-")
        scope_desc = f"{base_app} + all instances"
    else:
        target = _apply_instance(base_app, inst)
        def match(n: str) -> bool:
            return n == target
        scope_desc = target

    matches = [a for a in _list_apps()
               if match(_app_name(a)) and _is_live(_app_state(a))]
    if not matches:
        print(f"(no live app for {scope_desc})")
        return
    for a in matches:
        appid = _app_id(a)
        name = _app_name(a)
        print(f"→ modal app stop {appid} ({name})")
        subprocess.run(["modal", "app", "stop", appid], check=False)


def _live_container_app_ids() -> set[str]:
    """Cross-reference `modal container list` to know which app IDs actually
    have a running container right now (vs zombie ephemeral apps left over
    from crashed functions)."""
    try:
        out = subprocess.run(
            ["modal", "container", "list", "--json"],
            capture_output=True, text=True, check=True,
        ).stdout
        return {_app_id(c) for c in json.loads(out) if _app_id(c)}
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return set()


def _our_app_names() -> set[str]:
    """Set of `app_name` values declared by any non-`_` config in CONFIGS_DIR.
    Used to filter `modal app list` down to VMs launched via this CLI rather
    than every app in the shared workspace."""
    names: set[str] = set()
    for p in CONFIGS_DIR.glob("*.yml"):
        if p.name.startswith("_"):
            continue
        try:
            cfg = _load(p)
        except Exception:
            continue
        if cfg.get("app_name"):
            names.add(cfg["app_name"])
    return names


def _is_our_app(name: str, our_base: set[str]) -> bool:
    """An app is ours if its name equals one of our base app_names OR is a
    `<base>-<instance>` variant produced by `--instance`."""
    if name in our_base:
        return True
    return any(name.startswith(f"{b}-") for b in our_base)


def cmd_ls(args: argparse.Namespace) -> None:
    our_names = _our_app_names()
    live_app_ids = _live_container_app_ids()
    rows: list[tuple[str, str, str, str]] = []
    for a in _list_apps():
        name = _app_name(a)
        state = _app_state(a)
        if not _is_live(state) or not _is_our_app(name, our_names):
            continue
        appid = _app_id(a)
        kind = "running" if appid in live_app_ids else "zombie (no container)"
        rows.append((appid, name, state or "running", kind))
    if not rows:
        print("(no running modal-ssh VMs)")
        return
    wid = max(len(r[0]) for r in rows)
    wnm = max(len(r[1]) for r in rows)
    wst = max(len(r[2]) for r in rows)
    for appid, name, state, kind in rows:
        print(f"  {appid:<{wid}}  {name:<{wnm}}  {state:<{wst}}  {kind}")


def cmd_ssh(args: argparse.Namespace) -> None:
    cfg = _load(_resolve_cfg(args.config))
    base_job = cfg.get("job_name")
    if not base_job:
        sys.exit("config has no job_name field")
    inst = _validate_instance(args.instance)
    marker = f"modal-vm-{_apply_instance(base_job, inst)}"
    sshcfg_path = Path.home() / ".ssh" / "config"
    if not sshcfg_path.exists():
        sys.exit("~/.ssh/config not found — run `modal-ssh up` first")
    text = sshcfg_path.read_text()
    m = re.search(
        rf"# >>> {re.escape(marker)} >>>(.*?)# <<< {re.escape(marker)} <<<",
        text, re.S,
    )
    if not m:
        sys.exit(
            f"no ssh entry for `{marker}` — run "
            f"`modal-ssh up {args.config or 'default'}"
            f"{' --instance ' + inst if inst else ''}` first"
        )
    host_match = re.search(r"Host\s+(\S+)", m.group(1))
    if not host_match:
        sys.exit(f"malformed ssh entry for {marker}")
    os.execvp("ssh", ["ssh", host_match.group(1)])


def cmd_configs(args: argparse.Namespace) -> None:
    found = [p for p in sorted(CONFIGS_DIR.glob("*.yml")) if not p.name.startswith("_")]
    if not found:
        print(f"(no configs found in {CONFIGS_DIR})")
        return
    w = max(len(p.stem) for p in found)
    for p in found:
        try:
            cfg = _load(p)
        except Exception:
            cfg = {}
        print(f"  {p.stem:<{w}}  {cfg.get('base_image', '?')}")


# ── Entry point ──────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        prog="modal-ssh",
        description="Launch / list / ssh into / stop Modal GPU dev VMs.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # Shared --profile arg for every subcommand that calls `modal`.
    profile_parent = argparse.ArgumentParser(add_help=False)
    profile_parent.add_argument(
        "--profile",
        help="Modal profile name from ~/.modal.toml (default: the profile with active=true)",
    )

    p_up = sub.add_parser("up", parents=[profile_parent], help="launch a VM")
    p_up.add_argument("config", nargs="?", help="config name (default: `default`)")
    p_up.add_argument("--gpu", help="override gpu spec, e.g. B200:2 or H100")
    p_up.add_argument("--duration", type=float, help="override duration_hours")
    p_up.add_argument(
        "--instance",
        help="parallel-instance suffix: appends -<id> to app_name and job_name "
             "so multiple launches from the same yml stay independently stoppable.",
    )
    p_up.set_defaults(func=cmd_up)

    p_down = sub.add_parser("down", parents=[profile_parent], help="stop a VM")
    p_down.add_argument("config", nargs="?")
    p_down.add_argument("--instance", help="target a specific instance (same id as up)")
    p_down.add_argument(
        "--all", action="store_true",
        help="stop the base app AND every -<id> instance of it",
    )
    p_down.set_defaults(func=cmd_down)

    p_ls = sub.add_parser("ls", parents=[profile_parent], help="list running modal-ssh VMs")
    p_ls.set_defaults(func=cmd_ls)

    p_ssh = sub.add_parser("ssh", help="ssh into a running VM")
    p_ssh.add_argument("config", nargs="?")
    p_ssh.add_argument("--instance", help="connect to a specific instance")
    p_ssh.set_defaults(func=cmd_ssh)

    p_run = sub.add_parser("run", parents=[profile_parent], help="submit a bash script as a background job")
    p_run.add_argument("config", help="config name")
    p_run.add_argument("script", help="path to local bash script to run on the VM")
    p_run.add_argument("--gpu", help="override gpu spec, e.g. B200:2 or H100")
    p_run.add_argument("--duration", type=float, help="override duration_hours")
    p_run.add_argument("--instance", help="instance suffix (same as for up/down)")
    p_run.add_argument(
        "-f", "--foreground", action="store_true",
        help="stay attached (stream logs); default is detached (background)",
    )
    p_run.set_defaults(func=cmd_run)

    p_logs = sub.add_parser("logs", parents=[profile_parent], help="tail/replay an app's logs")
    p_logs.add_argument("config", nargs="?")
    p_logs.add_argument("--instance", help="target a specific instance")
    p_logs.set_defaults(func=cmd_logs)

    p_cfg = sub.add_parser("configs", help="list available config files")
    p_cfg.set_defaults(func=cmd_configs)

    args = p.parse_args()
    _apply_profile(getattr(args, "profile", None))
    args.func(args)


if __name__ == "__main__":
    main()
