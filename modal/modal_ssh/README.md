<p align="center">
  <img src="assets/modal_header.svg" alt="Modal SSH CLI" height="90">
</p>

YAML-driven CLI for Modal GPU VMs. Two modes share the same yml + image:

- **`up`**: Spin up a dev VM, auto-writes `~/.ssh/config` and opens a VSCode Remote-SSH window. Great for debugging, writing code, and interactive exploration.
- **`run`**: Submit a bash script to run in the Modal background and return immediately. Great for training, evaluation, and batch jobs.

## Mode Comparison

| | `modal-ssh up` | `modal-ssh run` |
|---|---|---|
| Container does | sshd blocks waiting for connections | Runs your bash script |
| Local side effects | Modifies `~/.ssh/config` + opens VSCode (auto) | Only prints log command hint |
| Best for | Debugging, coding, interactive exploration | Long training runs, batch eval, scheduled jobs |
| When it stops | `down` command or `duration_hours` expires | Script exits / `down` / expires |
| How to view output | SSH into the terminal | `modal-ssh logs <config>` |

## Quick Start

```bash
# One-time install
cd modal-runner
pip install -e .

# ── Interactive ──
modal-ssh up sglang               # Start a VM (first time: 5-15 min build)
modal-ssh ssh sglang              # SSH in (VSCode opens automatically)
modal-ssh down sglang             # Stop when done

# ── Background job ──
modal-ssh run mrp-train-test ./train.sh    # Submit → returns immediately
modal-ssh logs mrp-train-test              # View output (live stream or replay)
modal-ssh down mrp-train-test              # Clean up

# ── General ──
modal-ssh ls                      # List all running VMs
modal-ssh configs                 # List all available ymls
modal-ssh -h                      # Overall help
modal-ssh up -h                   # Subcommand help
```

---

## Prerequisites

**Required**

```bash
cd modal-runner && pip install -e .   # Register modal-ssh to PATH
modal setup                            # Modal authentication (if not done yet)
```

**Optional (depending on your yml)**

| Prerequisite | When needed | How to set up |
|---|---|---|
| `huggingface-secret` Modal secret | yml references it in `secrets:` (default) | `modal secret create huggingface-secret HF_TOKEN=hf_yourtoken` |
| `~/.ssh/id_ed25519_modal` | Enabled by default | Auto-generated via `ssh-keygen` on first run |
| `~/.ssh/id_ed25519_github` | yml enables `github_ssh_key` (some templates) | Generate local key and add to GitHub, or comment out that line in yml |
| `code` CLI on PATH | yml has `open_vscode: true` | VSCode: `Cmd+Shift+P → Shell Command: Install 'code' command in PATH` |
| VSCode remote platform default | Avoid platform prompt on each connection | Add `"remote.SSH.remotePlatform": {"*": "linux"}` to `settings.json` |

Optional items are not required — missing ones will report errors at the relevant step.

---

## Command Reference

| Command | Description |
|---|---|
| `modal-ssh up <config> [options]` | Start a dev VM with sshd listening and open VSCode Remote-SSH window |
| `modal-ssh ssh <config> [--instance ID]` | SSH into a VM started with `up` |
| `modal-ssh down <config> [--instance ID \| --all]` | Stop a VM |
| `modal-ssh ls` | List all live apps started by modal-ssh |
| `modal-ssh run <config> <script> [options]` | Submit a bash script as a background job |
| `modal-ssh logs <config> [--instance ID]` | Tail or replay job logs |
| `modal-ssh configs` | List available ymls |

See subsections below for per-command options.

---

## Command Details

### `modal-ssh up <config> [options]`

Start a dev VM using the `<config>` yml. `<config>` can be a short name (`sglang`), filename (`sglang.yml`), or full path. Defaults to `configs/default.yml` if omitted.

| Option | Description |
|---|---|
| `--gpu <spec>` | Override GPU temporarily, e.g. `B200:2` / `H100` / `A10G:1` |
| `--duration <hours>` | Override container lifetime |
| `--instance <id>` | Append `-<id>` suffix to `app_name` and `job_name` to run multiple instances of the same yml |

```bash
modal-ssh up sglang                                  # Use yml defaults
modal-ssh up sglang --gpu A100:1 --duration 1        # One A100 for 1 hour
modal-ssh up mrp-train-test --instance a             # Parallel instance mrp-train-test-a
```

### `modal-ssh ssh <config> [--instance ID]`

Looks up the host written by the last `up` via the marker `modal-vm-<job_name>[-<instance>]` in `~/.ssh/config`, then runs `exec ssh <host>`. **Does not start a new VM** — the VM must already be running. Equivalent to typing `ssh <host>` locally.

```bash
modal-ssh ssh sglang
modal-ssh ssh mrp-train-test --instance a
```

### `modal-ssh down <config> [--instance ID | --all]`

Stop the VM for the specified yml.

| Usage | Behavior |
|---|---|
| `modal-ssh down sglang` | Stop all live instances where `app_name == "sglang-ssh"` (no `--instance` suffix) |
| `modal-ssh down mrp-train-test --instance b` | Stop only `mrp-train-test-b` |
| `modal-ssh down mrp-train-test --all` | Stop base + all `-X`-suffixed instances |

```bash
modal-ssh down sglang
modal-ssh down mrp-train-test --instance b
modal-ssh down mrp-train-test --all
```

### `modal-ssh ls`

Shows **live apps started by this CLI** — filtered by `app_name` declared in `configs/*.yml`.

```
ap-XXXX...   sglang-ssh         ephemeral (detached)  running
ap-YYYY...   mrp-train-test-a   ephemeral (detached)  running
ap-ZZZZ...   mrp-train-test-b   ephemeral (detached)  zombie (no container)
```

- **running** = container is active
- **zombie** = Modal app state is alive but the container has died. Not billed, just a stale state record. `down` will clean it up.

### `modal-ssh run <config> <script> [options]`

Submit a local `<script>` as a background job. The container runs this script instead of sshd and terminates naturally when the script exits (or crashes).

| Option | Description |
|---|---|
| `--gpu <spec>` | Override GPU |
| `--duration <hours>` | Override lifetime |
| `--instance <id>` | Parallel instance suffix (same as `up`) |
| `-f` / `--foreground` | Don't detach; stream stdout locally |

```bash
modal-ssh run mrp-train-test ./train.sh                    # Submit, detach, return
modal-ssh run mrp-train-test ./train.sh -f                 # Foreground, stream locally
modal-ssh run mrp-train-test ./train.sh --instance exp1
modal-ssh run mrp-train-test ./quick.sh --gpu A10G:1 --duration 1
```

The script **automatically activates the conda environment set during yml build** (e.g. `llamafactory_sdar`). Variables in `shell_env` (e.g. `HF_TOKEN`) are available directly in the script — **no need to manually** `conda activate` or `source`.

### `modal-ssh logs <config> [--instance ID]`

Internally runs `modal app logs <app_id>`:
- Container still running → live stream (Ctrl+C exits but does not kill the container)
- Container already stopped → historical replay

Logs are **stored on Modal's backend**, not downloaded locally. Modal purges them after a retention period — redirect to a file for permanent archiving.

```bash
modal-ssh logs mrp-train-test
modal-ssh logs mrp-train-test --instance exp1
modal-ssh logs mrp-train-test --instance exp1 > exp1.log   # Archive
```

### `modal-ssh configs`

Lists `configs/*.yml` (skips `_`-prefixed files) with the base image for each:

```
  default          nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04
  sglang           lmsysorg/sglang:latest
  mrp-train        nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04
  mrp-train-test   nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04
  mrp-eval         nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04
```

---

## Common Workflows

### 1. Start a dev VM for coding

```bash
modal-ssh up sglang                       # Wait for build, VSCode opens automatically
# (Write code and run experiments in VSCode Remote window)
modal-ssh down sglang                     # Shut down when done
```

### 2. Multiple SSH sessions to the same VM

```bash
modal-ssh up sglang                       # VSCode already opened; want a terminal too
modal-ssh ssh sglang                      # Open an SSH terminal
modal-ssh ssh sglang                      # Open another; they're independent
```

### 3. Run a one-off training job

```bash
modal-ssh run mrp-train-test ./train.sh   # Submit and walk away
# Hours later:
modal-ssh ls                              # Check if still running
modal-ssh logs mrp-train-test             # View logs
modal-ssh down mrp-train-test             # Clean up zombie state after it finishes
```

### 4. Run multiple parallel experiments (each independently stoppable)

```bash
modal-ssh run mrp-train-test ./train.sh --instance lr_1e-3
modal-ssh run mrp-train-test ./train.sh --instance lr_5e-4
modal-ssh run mrp-train-test ./train.sh --instance lr_1e-4

modal-ssh ls                                          # See 3 entries
modal-ssh logs mrp-train-test --instance lr_1e-3      # View output for one
modal-ssh down mrp-train-test --instance lr_5e-4      # Cancel a bad one
modal-ssh down mrp-train-test --all                   # Clean up all when done
```

### 5. Dev VM and background job from the same yml simultaneously

```bash
modal-ssh up  mrp-train-test --instance dev          # Dev VM to SSH into
modal-ssh run mrp-train-test ./batch.sh --instance batch1   # Concurrent background job
modal-ssh run mrp-train-test ./batch.sh --instance batch2   # Another one
# Three independent apps, no conflicts
```

### 6. Smoke test with a cheaper small GPU first

```bash
modal-ssh run mrp-train-test ./smoke.sh --gpu A10G:1 --duration 1 --instance smoke
modal-ssh logs mrp-train-test --instance smoke
modal-ssh down mrp-train-test --instance smoke
```

### 7. Cloning a private repo

Enable `github_ssh_key: ~/.ssh/id_ed25519_github` in the yml (add this local key to your GitHub account), then set `git_repo: git@github.com:org/repo.git` in the yml — it will be cloned during the image build.

---

## YAML Configuration

### Automatic `_base.yml` merge

`configs/_base.yml` holds **shared defaults** and is automatically deep-merged *under* the specific yml on every VM start. `modal-ssh configs` skips it.

Merge rules:

| Field type | Behavior |
|---|---|
| dict | Recursive merge; union of keys; specific yml wins on conflict |
| list | **Wholesale replacement** — base list is discarded |
| scalar (string/number/bool) | Replacement |

**The list replacement gotcha**: if base has `apt_packages: [openssh-server, git, ...]` and you want to add `build-essential`, **you must list every package**:

```yaml
# Wrong: this drops the 6 packages from base
apt_packages: [build-essential]

# Correct:
apt_packages: [openssh-server, git, wget, curl, tmux, vim, build-essential]
```

**The dict incremental merge convenience**: base has `volumes: {/root/.cache/huggingface: huggingface-cache}`; you only need to add new entries:

```yaml
volumes:
  /root/checkpoints: my-ckpts        # Merges with base's HF cache; both take effect
```

### Supported YAML Fields

| Field | Description |
|---|---|
| `app_name` | App name shown in Modal; used by `down` / `ls` / `logs` for matching |
| `job_name` | SSH config marker name `modal-vm-<job_name>`; used by `ssh` to locate the host |
| `open_vscode` | bool — whether to auto-open VSCode Remote-SSH after VM is ready |
| `base_image` | Container base image |
| `add_python` | Python version for Modal to add to the base image (omit if base already includes Python) |
| `gpu.type` / `gpu.count` | e.g. `H100` / `4` |
| `duration_hours` | Container lifetime; auto-stops when expired |
| `ssh_public_keys` | List of local pubkeys to inject into `authorized_keys` (first one's private key used as default IdentityFile) |
| `github_ssh_key` | Optional — local GitHub private key path, baked into image to allow `git clone` of private repos inside the container |
| `git_repo` | Optional — repo to `git clone` at build time; string or `{url, dest}` |
| `apt_packages` | Packages to `apt install` at build time |
| `run_commands` | Extra shell commands to run at build time (each becomes an image layer) |
| `volumes` | `mount_path: volume_name` dict; mounts Modal Volumes for persistence |
| `secrets` | List of Modal Secret names |
| `shell_env` | Env vars exported to `/root/.profile` + `/root/.bashrc`. Values can reference container-side env with `$VAR` (e.g. `$HF_TOKEN` injected by a secret) |
| `local_files` | Optional — `local_path: remote_path` dict; bakes local files into the image |
| `auto_generate_modal_key` | bool, default true — auto `ssh-keygen` if `~/.ssh/id_ed25519_modal` doesn't exist |

### Available Configs

| File | Purpose |
|---|---|
| `_base.yml` | Shared defaults; merged in, not a direct entry point |
| `default.yml` | Minimal GPU VM — ubuntu + cuda + Python, no extra environment |
| `sglang.yml` | sglang dev environment (`lmsysorg/sglang:latest` base + conda + sglang) |
| `mrp-train.yml` | multi-token-denoising training env (conda + torch cu128 + flash-attn + private repo) |
| `mrp-eval.yml` | opencompass eval env (conda + torch + flash-attn + vllm + opencompass) |
| `mrp-train-test.yml` | Isolated personal test env mirroring mrp-train but with `-test` suffix on `app_name`/`job_name` |

---

## Parallel Instances (`--instance`)

Without `--instance`, `down` will **stop all instances at once** (matched by app_name). Use `--instance` to preserve independent stop control:

```bash
modal-ssh up  mrp-train-test --instance a          # app_name becomes mrp-train-test-a
modal-ssh run mrp-train-test ./t.sh --instance b   # Same yml, background job, becomes mrp-train-test-b

modal-ssh ls                                       # Two entries
modal-ssh down mrp-train-test --instance a         # Stop only a; b continues
modal-ssh down mrp-train-test --all                # Stop base + all -X instances
```

`--instance` appends the suffix to both `app_name` and `job_name`, so:

- Modal sees N independent apps; `down` / `ls` / `logs` can target each precisely
- `~/.ssh/config` gets N independent marker blocks `modal-vm-<job>-<id>`, no overwrites
- All instances share the same image cache (suffix is not baked into the image env) — build once, subsequent instance starts are fast

**Volume sharing caveat**: `volumes:` is defined in the yml and all instances **share the same volume**. HF cache (mostly reads) is fine; **do not write checkpoints to the same volume** — either duplicate the yml per experiment, or use different subdirectories in the training script (e.g. `/root/checkpoints/run-a/`, `/root/checkpoints/run-b/`).

---

## Repository Structure

```
modal-runner/
├── modal_ssh.py            # Modal app + container sshd + local launcher (all-in-one)
├── modal_ssh_cli.py        # CLI entry point (up/down/ls/ssh/run/logs/configs)
├── pyproject.toml          # console_scripts registration for modal-ssh
├── README.md               
├── configs/
│   ├── _base.yml           # Shared defaults; auto-merged
│   ├── default.yml
│   ├── sglang.yml
│   ├── mrp-train.yml
│   ├── mrp-eval.yml
│   └── mrp-train-test.yml
└── scripts/
    └── download_models.sh  # In-VM utility; unrelated to the launch stack
```