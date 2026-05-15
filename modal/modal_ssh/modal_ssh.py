"""Modal SSH dev VM — image build + container sshd + local-side launcher.

This module plays three roles in one file:

  1. At module import time (on your laptop): loads the YAML config and
     declaratively builds a `modal.Image` from it.
  2. Inside the Modal container (`launch_ssh`): starts sshd and exposes
     port 22 through `modal.forward`.
  3. In the local entrypoint (`main`): receives host:port back through a
     Queue, writes a managed block into `~/.ssh/config`, probes SSH, and
     opens VSCode Remote-SSH.

Designed for `modal run --detach`. Prefer invoking via the `modal-ssh` CLI:
    modal-ssh up sglang
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import modal
import yaml


# ─────────────────────────────────────────────────────────────────────────
# Config loading (with optional configs/_base.yml deep-merge)
# ─────────────────────────────────────────────────────────────────────────
def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base or {})
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_config(path: str) -> dict:
    """Load `path`; if `<path's dir>/_base.yml` exists, merge base under it."""
    cfg_p = Path(path)
    cfg = yaml.safe_load(cfg_p.read_text()) or {}
    base = cfg_p.parent / "_base.yml"
    if base.exists() and base.resolve() != cfg_p.resolve():
        cfg = _deep_merge(yaml.safe_load(base.read_text()) or {}, cfg)
    return cfg


CONFIG_PATH = os.environ.get("CONFIG", str(Path(__file__).parent / "configs" / "default.yml"))
cfg = _load_config(CONFIG_PATH)

# CLI-driven overrides (set by modal_ssh_cli.py — keep them simple).
if (g := os.environ.get("MODAL_SSH_GPU")):
    t, _, c = g.partition(":")
    cfg["gpu"] = {"type": t, "count": int(c or 1)}
if (d := os.environ.get("MODAL_SSH_DURATION")):
    cfg["duration_hours"] = float(d)

# Instance suffix: `--instance a` on the CLI suffixes `-a` onto app_name and
# job_name so multiple parallel launches of the same yml stay independently
# stoppable / sshable. Does NOT get baked into the image .env (would bust
# the image cache per-instance) — only the local-side registration uses it.
if (inst := os.environ.get("MODAL_SSH_INSTANCE", "").strip()):
    cfg["app_name"] = f"{cfg['app_name']}-{inst}"
    cfg["job_name"] = f"{cfg['job_name']}-{inst}"


# ─────────────────────────────────────────────────────────────────────────
# Auto-generate dedicated Modal SSH key on the user's laptop
# ─────────────────────────────────────────────────────────────────────────
def _ensure_modal_key(path: Path = Path.home() / ".ssh" / "id_ed25519_modal") -> None:
    pub = Path(str(path) + ".pub")
    if path.exists() and pub.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(path), "-N", "", "-C", "modal-vm"],
        check=True,
    )
    print(f"Generated new Modal SSH key: {path}")


if modal.is_local() and cfg.get("auto_generate_modal_key", True):
    _ensure_modal_key()

pubkey_paths = [Path(p).expanduser() for p in cfg["ssh_public_keys"]]
if modal.is_local():
    for p in pubkey_paths:
        assert p.exists(), f"SSH public key not found: {p}"
DEFAULT_KEY_PATH = Path(str(pubkey_paths[0]).removesuffix(".pub"))


# ─────────────────────────────────────────────────────────────────────────
# Single source of truth for git_repo dest
# ─────────────────────────────────────────────────────────────────────────
def _resolve_repo(c: dict) -> tuple[str | None, str | None]:
    r = c.get("git_repo")
    if not r:
        return None, None
    if isinstance(r, dict):
        url, dest = r["url"], r.get("dest")
    else:
        url, dest = r, None
    return url, dest or f"/root/{Path(url.rstrip('/')).name.removesuffix('.git')}"


REPO_URL, REPO_DEST = _resolve_repo(cfg)


# ─────────────────────────────────────────────────────────────────────────
# Image build (runs at module import, on your laptop)
#
# Modal re-imports this module inside the container at startup to locate
# the function — so the container needs (a) `configs/` available on disk
# at the same logical path AND (b) pyyaml installed AND (c) the CONFIG env
# var pointing at the container-side copy. Otherwise the top-level
# `_load_config(CONFIG_PATH)` call crashes inside the container.
# ─────────────────────────────────────────────────────────────────────────
_local_configs_dir = str(Path(CONFIG_PATH).resolve().parent)
_container_config_path = f"/root/configs/{Path(CONFIG_PATH).name}"

_from_kwargs = {"add_python": cfg["add_python"]} if cfg.get("add_python") else {}
image = (
    modal.Image.from_registry(cfg["base_image"], **_from_kwargs)
    .entrypoint([])
    .env({"DEBIAN_FRONTEND": "noninteractive", "TZ": "UTC"})
    .apt_install(*cfg.get("apt_packages", []))
)

# Inject every configured public key into authorized_keys.
for i, p in enumerate(pubkey_paths):
    image = image.add_local_file(str(p), f"/root/.ssh/keys/key_{i}.pub", copy=True)

image = image.run_commands(
    "mkdir -p /root/.ssh /run/sshd",
    "cat /root/.ssh/keys/*.pub > /root/.ssh/authorized_keys",
    "chmod 700 /root/.ssh",
    "chmod 600 /root/.ssh/authorized_keys",
    "ssh-keygen -A",
    "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config",
    "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config",
)

# Optional: upload a GitHub private key so `git clone git@github.com:...` works
# inside the VM. WARNING: bakes the private key into the image cache.
if cfg.get("github_ssh_key"):
    gk = Path(cfg["github_ssh_key"]).expanduser()
    if modal.is_local():
        assert gk.exists(), f"github_ssh_key not found: {gk}"
    image = image.add_local_file(str(gk), "/root/.ssh/id_ed25519_github", copy=True)
    image = image.run_commands(
        "chmod 600 /root/.ssh/id_ed25519_github",
        "printf 'Host github.com\\n  HostName github.com\\n  User git\\n  IdentityFile /root/.ssh/id_ed25519_github\\n  StrictHostKeyChecking no\\n' >> /root/.ssh/config",
        "chmod 600 /root/.ssh/config",
        "ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null || true",
    )

# Optional: copy arbitrary local files into the image.
for local_path, remote_path in (cfg.get("local_files") or {}).items():
    le = Path(local_path).expanduser()
    if modal.is_local():
        assert le.exists(), f"local_files entry not found: {le}"
    image = image.add_local_file(str(le), remote_path, copy=True)

# Optional: clone a single git repo into the image at build time.
if REPO_URL:
    image = image.run_commands(
        f"mkdir -p {os.path.dirname(REPO_DEST)}",
        f"git clone {REPO_URL} {REPO_DEST}",
    )

# Extra build-time shell commands.
if cfg.get("run_commands"):
    image = image.run_commands(*cfg["run_commands"])

# Bake pyyaml + configs/ + CONFIG env into the image LAST so they don't
# bust the cache of the heavy run_commands chain above. The container
# needs all three at startup because Modal re-imports this module to find
# the function definition, which re-runs `_load_config(CONFIG_PATH)` at
# the top of this file — and CONFIG must point at the container-side path.
image = (
    image
    .pip_install("pyyaml")
    .add_local_dir(_local_configs_dir, "/root/configs", copy=True)
    .env({"CONFIG": _container_config_path})
)


# ─────────────────────────────────────────────────────────────────────────
# App + Function (Function body runs inside the Modal container)
# ─────────────────────────────────────────────────────────────────────────
GPU_SPEC = (
    f"{cfg['gpu']['type']}:{cfg['gpu']['count']}"
    if cfg["gpu"]["count"] > 1 else cfg["gpu"]["type"]
)
TIMEOUT_S = int(float(cfg["duration_hours"]) * 3600)

volumes = {
    mnt: modal.Volume.from_name(name, create_if_missing=True)
    for mnt, name in (cfg.get("volumes") or {}).items()
}
app = modal.App(cfg["app_name"], image=image, volumes=volumes)


def _wait_for_sshd(host: str, port: int, q: modal.Queue) -> None:
    """In the container: don't report host:port until sshd has bound 22."""
    start = time.monotonic()
    while True:
        try:
            with socket.create_connection(("localhost", 22), timeout=30.0):
                break
        except OSError as exc:
            if time.monotonic() - start >= 60.0:
                raise TimeoutError("sshd never bound 22") from exc
            time.sleep(0.1)
    q.put((host, port))


def _write_shell_env(shell_env: dict) -> None:
    """Persist shell_env into .profile and .bashrc so both login and
    non-login shells (e.g. VSCode terminals, bash -lc invocations) see them."""
    for target in ("/root/.profile", "/root/.bashrc"):
        with open(target, "a") as f:
            for k, v in shell_env.items():
                v = os.path.expandvars(v) if isinstance(v, str) else v
                f.write(f'export {k}="{v}"\n')


@app.function(
    gpu=GPU_SPEC,
    timeout=TIMEOUT_S,
    secrets=[modal.Secret.from_name(s) for s in (cfg.get("secrets") or [])],
)
def launch_ssh(q: modal.Queue, shell_env: dict) -> None:
    _write_shell_env(shell_env)
    with modal.forward(22, unencrypted=True) as tunnel:
        host, port = tunnel.tcp_socket
        threading.Thread(target=_wait_for_sshd, args=(host, port, q)).start()
        subprocess.run(["/usr/sbin/sshd", "-D"])


@app.function(
    gpu=GPU_SPEC,
    timeout=TIMEOUT_S,
    secrets=[modal.Secret.from_name(s) for s in (cfg.get("secrets") or [])],
)
def launch_job(script_content: str, shell_env: dict) -> int:
    """Run a bash script in this image. stdout/stderr go to Modal logs,
    retrievable via `modal-ssh logs <config>` after detach.

    Gives the script the same conda env that `modal-ssh ssh` would land in.
    We can't just `bash -lc` because Ubuntu's default `.bashrc` returns early
    for non-interactive shells (the standard `case $- in *i*) ;; *) return;;`
    preamble), which means `conda activate <env>` from .bashrc never runs.
    Instead we source conda.sh + activate explicitly in a wrapper.
    """
    _write_shell_env(shell_env)
    script_path = "/root/_modal_ssh_job.sh"
    Path(script_path).write_text(script_content)
    os.chmod(script_path, 0o755)

    wrapper_path = "/root/_modal_ssh_wrapper.sh"
    Path(wrapper_path).write_text(
        "#!/bin/bash\n"
        "# Replicate the conda activate behaviour of an interactive ssh login.\n"
        "if [ -f /root/miniconda3/etc/profile.d/conda.sh ]; then\n"
        "    source /root/miniconda3/etc/profile.d/conda.sh\n"
        "    env_name=$(grep -oE 'conda activate [A-Za-z0-9._-]+' /root/.bashrc 2>/dev/null | tail -1 | awk '{print $3}')\n"
        "    if [ -n \"$env_name\" ]; then\n"
        "        conda activate \"$env_name\" && echo \"[modal-ssh job] activated conda env: $env_name\"\n"
        "    fi\n"
        "fi\n"
        f"exec bash {script_path}\n"
    )
    os.chmod(wrapper_path, 0o755)

    # `bash -l` so .profile (containing shell_env exports we just wrote) is
    # sourced before the wrapper runs.
    print("[modal-ssh job] starting", flush=True)
    rc = subprocess.run(["bash", "-l", wrapper_path]).returncode
    print(f"[modal-ssh job] exited rc={rc}", flush=True)
    return rc


# ─────────────────────────────────────────────────────────────────────────
# Local-side helpers (replaces launch.sh; runs on your laptop)
# ─────────────────────────────────────────────────────────────────────────
_MARKER_BEGIN_RE = re.compile(r"^# >>> (modal-vm[^>]*?) >>>$")


def _update_ssh_config(
    host: str, port: int, key_path: Path, marker: str,
    ssh_config_path: Path = Path.home() / ".ssh" / "config",
) -> None:
    """Maintain a single marker-keyed block in ~/.ssh/config.

    Drops (a) any previous block with the same marker, and (b) any other
    modal-vm-prefixed block whose Host line matches `host` — this prevents
    a stale port from a previous launch (with a different marker, e.g. an
    older `modal-vm` from launch.sh) from overriding the freshly-written
    port when Modal recycles the same `rNNN.modal.host` name.
    """
    ssh_config_path.parent.mkdir(parents=True, exist_ok=True)
    ssh_config_path.touch()

    lines = ssh_config_path.read_text().splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _MARKER_BEGIN_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        # Collect the full marker block.
        block_marker = m.group(1)
        block_end = f"# <<< {block_marker} <<<"
        block = [lines[i]]
        i += 1
        block_host: str | None = None
        while i < len(lines):
            block.append(lines[i])
            h = re.match(r"^\s*Host\s+(\S+)", lines[i])
            if h and block_host is None:
                block_host = h.group(1)
            if lines[i] == block_end:
                i += 1
                break
            i += 1
        # Drop the block if it matches the marker we're rewriting OR points
        # at the same host (any modal-vm-* block); otherwise keep it.
        if block_marker == marker or block_host == host:
            continue
        out.extend(block)

    out += [
        f"# >>> {marker} >>>",
        f"Host {host}",
        f"    Port {port}",
        f"    User root",
        f"    IdentityFile {key_path}",
        f"    StrictHostKeyChecking no",
        f"    UserKnownHostsFile /dev/null",
        f"# <<< {marker} <<<",
    ]
    ssh_config_path.write_text("\n".join(out) + "\n")


def _probe_ssh(host: str, timeout_s: int = 120, connect_timeout_s: int = 5) -> bool:
    """End-to-end SSH handshake check (covers Modal-tunnel propagation).
    Retries until the wall-clock budget runs out rather than a fixed count.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        rc = subprocess.run(
            ["ssh", "-o", f"ConnectTimeout={connect_timeout_s}",
             "-o", "BatchMode=yes",
             "-o", "StrictHostKeyChecking=no",
             "-o", "UserKnownHostsFile=/dev/null", host, "true"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode
        if rc == 0:
            return True
        time.sleep(2)
    return False


@app.local_entrypoint()
def main() -> None:
    """Runs on your laptop under `modal run`. Dispatches on MODAL_SSH_MODE:
      - "ssh" (default): start sshd in the container + write ~/.ssh/config
                          + probe + open VSCode Remote-SSH
      - "job"          : read MODAL_SSH_SCRIPT locally, ship its contents
                          to a launch_job container call, return
    """
    if os.environ.get("MODAL_SSH_MODE", "ssh") == "job":
        _run_job_mode()
    else:
        _run_ssh_mode()


def _run_ssh_mode() -> None:
    print(f"Config: {CONFIG_PATH}")
    print(f"GPU: {GPU_SPEC}  |  Duration: {cfg['duration_hours']}h")

    with modal.Queue.ephemeral() as q:
        launch_ssh.spawn(q, cfg.get("shell_env") or {})
        host, port = q.get(timeout=600)

        print(f"\nApp: {app.name}")
        print(
            f"  ssh -i {DEFAULT_KEY_PATH} -p {port} "
            f"-o StrictHostKeyChecking=no root@{host}"
        )

        if os.environ.get("MODAL_SSH_NO_LAUNCH"):
            print("(MODAL_SSH_NO_LAUNCH set — skipping local-side launcher)")
            return

        marker = f"modal-vm-{cfg['job_name']}"
        _update_ssh_config(host, port, DEFAULT_KEY_PATH, marker)
        print(f"→ ~/.ssh/config updated (marker `{marker}`)")
        print(f"  shortcut: ssh {host}")

        if not _probe_ssh(host):
            print(
                "⚠ SSH probe did not succeed within budget — "
                f"VSCode skipped. Try manually: `ssh {host}`"
            )
            return
        print("→ SSH reachable")

        if cfg.get("open_vscode", True):
            if shutil.which("code"):
                remote_dir = REPO_DEST or "/root"
                subprocess.Popen(
                    ["code", "--folder-uri",
                     f"vscode-remote://ssh-remote+{host}{remote_dir}"]
                )
                print(f"→ VSCode opened at {remote_dir}")
            else:
                print("(`code` CLI not on PATH — skipping VSCode launch)")


def _run_job_mode() -> None:
    script_path = os.environ.get("MODAL_SSH_SCRIPT", "")
    if not script_path:
        raise SystemExit("MODAL_SSH_MODE=job but MODAL_SSH_SCRIPT is not set")
    p = Path(script_path)
    if not p.is_file():
        raise SystemExit(f"script not found: {script_path}")
    script_content = p.read_text()

    print(f"Config: {CONFIG_PATH}")
    print(f"GPU: {GPU_SPEC}  |  Duration: {cfg['duration_hours']}h")
    print(f"Job:  {p.name}")
    print(f"App:  {app.name}")

    launch_job.spawn(script_content, cfg.get("shell_env") or {})
    print("→ job submitted (detached). Useful next steps:")
    print(f"    modal-ssh logs   {cfg['app_name']}")
    print(f"    modal-ssh ls")
    print(f"    modal-ssh down   {cfg['app_name']}")
