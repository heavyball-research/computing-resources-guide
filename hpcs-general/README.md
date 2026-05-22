<p align="center">
  <img src="assets/hpcs_header.svg" alt="HPC in General" height="90">
</p>

This section aims to introduce some beginner to advanced topics that are generally applicable to many HPC systems. We would only cover HPC-related topics for now and will not discuss the more general topics that are relevant to operating systems or Linux CLI.

## HPC mental model

An HPC cluster is not "a bigger Linux box" — it's a shared, scheduled, multi-machine system. The diagram below shows the pieces and who owns what:

```
                       ┌────────────────────────────┐
                       │       Your laptop          │  [YOU]
                       └─────────────┬──────────────┘
                                     │ ssh
                                     ▼
   ╔═══════════════════════════ HPC cluster ══════════════════════════╗
   ║                                                                  ║
   ║   ┌──────────────────┐    sbatch / srun    ┌──────────────────┐  ║
   ║   │   Login node     │ ───────────────────▶│   Slurm queue    │  ║
   ║   │ hardware: ADMIN  │                     │ owned by: ADMIN  │  ║
   ║   │ your shell: YOU  │                     │ your jobs in it: │  ║
   ║   │ edit · submit    │                     │       YOU        │  ║
   ║   └────────┬─────────┘                     └────────┬─────────┘  ║
   ║            │                                        │ dispatch   ║
   ║            │ your shell                             ▼            ║
   ║            │                              ┌───────────────────┐  ║
   ║            │                              │  Compute nodes    │  ║
   ║            │                              │ hardware: ADMIN   │  ║
   ║            │                              │ your job's slice: │  ║
   ║            │                              │      YOU          │  ║
   ║            │                              └─────────┬─────────┘  ║
   ║            ▼                                        ▼            ║
   ║   ┌────────────────────────────────────────────────────────┐     ║
   ║   │  Shared filesystems: $HOME · $SCRATCH · project        │     ║
   ║   │  mount points & quotas: ADMIN                          │     ║
   ║   │  files inside your $HOME / project space: YOU          │     ║
   ║   └────────────────────────────────────────────────────────┘     ║
   ║                                                                  ║
   ╚══════════════════════════════════════════════════════════════════╝
```

**Login node vs compute node**

When you `ssh` to a cluster, you land on a **login node** — a small shared box meant for editing files, submitting jobs, and light shell work. Real work (training, eval, anything touching a GPU, even a heavy `pip install`) belongs on a **compute node**, which you request from Slurm. Rule of thumb: if a command takes more than ~1 min of CPU or touches a GPU, it doesn't run on the login node.

## The Slurm system

Slurm is the scheduler that hands out compute nodes. You describe a job (CPUs, memory, GPUs, wall-time, partition / account) and Slurm decides when and where it runs. Two ways to invoke it:

**Interactive mode**

`srun --pty bash` (or the `gpu` / `cpu` helpers in [my .bashrc](./.bashrc)) gives you a live shell on a compute node. Great for debugging, manual installs, and quick experiments. The shell dies when you disconnect, so wrap it in `tmux` if you want it to survive a network blip.

```bash
gpu 8 64 4 1     # 8 CPUs, 64 GB RAM, 4 hours, 1 GPU
```

**Sbatch mode**

`sbatch script.sh` submits a batch job: Slurm queues it, runs it whenever resources are free, writes stdout/stderr to a file, and doesn't care whether your laptop is awake. Default for any real training run.

```bash
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --account=my_project_account
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --gres=gpu:4
#SBATCH --constraint="h100"
#SBATCH --time=24:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --mail-user=you@example.com
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --dependency=afterok:123456
#SBATCH --requeue

python train.py
```

<details>
<summary>What each flag does</summary>

- `--job-name` — human-readable name; shows up in `squeue` and is the `%x` token in output paths.
- `--account` — billing account / allocation to charge the job against. Required on most shared clusters.
- `--partition` — which pool of nodes to run on (e.g. `gpu`, `cpu`, `debug`). Each partition has its own limits and priorities.
- `--nodes` — number of physical machines to reserve. `1` for single-node multi-GPU; `>1` for multi-node distributed training.
- `--cpus-per-task` — CPU cores allocated per task. Tune for your dataloader workers.
- `--mem` — host RAM per node. Independent of GPU memory.
- `--gres=gpu:N` — number of GPUs per node (generic resources).
- `--constraint` — feature filter on nodes, e.g. `"h100"`, `"a100|h100"` (either), `"a100&nvlink"` (both). Use to pin yourself to specific GPU models or interconnects.
- `--time` — wall-clock limit (`HH:MM:SS` or `D-HH:MM:SS`). Slurm kills the job when it expires; shorter requests usually start sooner.
- `--output` — file for stdout. `%x` = job name, `%j` = job ID, `%a` = array index.
- `--error` — file for stderr. Omit to merge into `--output`.
- `--mail-user` — email address for notifications.
- `--mail-type` — when to email: `BEGIN`, `END`, `FAIL`, `REQUEUE`, `TIME_LIMIT_80`, or `ALL`. Comma-separated.
- `--dependency` — gate this job on another. `afterok:JID` runs only if `JID` succeeded; also `afterany`, `afternotok`, `singleton`.
- `--requeue` — let Slurm auto-resubmit the job if a node fails or it gets preempted. Pair with checkpointing so you don't lose work.

</details>

Watch the queue with `sq`, inspect a specific job with `show <jobid>`, cancel with `scancel <jobid>`.

## Software stack (modules / conda / pip)

You don't have root on an HPC, so software gets layered:

1. **System modules** — `module load cuda/12.4 gcc/11`. Toolchain stuff curated by the admins. Load these _before_ creating conda envs that compile against CUDA.
2. **Conda / mamba** — owns Python versions and binary deps (pytorch, cudnn). One env per project, never install into `base`.
3. **pip** inside that env — pure-Python and source-built wheels.

Build heavyweight wheels (`flash-attn`, `xformers`) **on a compute node** with the same CUDA module your training job will use — never on the login node.

## Sharing files

On a shared cluster, the two tools that decide who can read/write your files are `chmod` (POSIX permissions) and `setfacl` (finer-grained ACLs). **Prefer `setfacl`** for day-to-day sharing: it lets you grant access to specific users without dragging them into a Unix group, and revoking access is a single `-x` instead of re-juggling group membership. Reach for `chmod` for the baseline (owner-only / locking files down) and `setfacl` for "share with these people." Always sanity-check with `ls -ld <path>` and `getfacl <path>` before assuming a file is private.

**`chmod` — POSIX permissions**

POSIX gives three permission classes: **user** (owner), **group**, **other** (everyone else). Each gets some combination of `r`/`w`/`x`.

```bash
# Inspect current perms
ls -ld my_dir
# drwxr-x---  2 alice alice  4096 May 22 14:00 my_dir
#  ^^^                  ← owner=alice, group=alice
#  └── u=rwx, g=r-x, o=--- → only `alice` and her group can read

# Let your groupmates read + traverse into the dir
chmod g+rx my_dir

# Open a single file to all users on the cluster
chmod o+r dataset.csv

# Lock a file down to just you
chmod 600 secret.env       # u=rw, g=---, o=---

# Apply recursively to a tree (capital -X = +x only on dirs/already-exec files)
chmod -R g+rX shared_dataset/

# Change the group ownership first if needed (so g+r actually targets the right people)
chgrp my_lab_group shared_dataset/
chmod -R g+rX shared_dataset/
```

**`setfacl` — ACLs for "share with one specific user"**

`chmod` only knows owner/group/other. If you want to grant access to one user without making them a groupmate, use ACLs:

```bash
# Inspect ACLs
getfacl my_dir

# Give user `bob` read+execute on a directory
setfacl -m u:bob:rx my_dir

# Give bob read+write+execute on the whole tree, AND on anything created later
setfacl -R -m u:bob:rwx my_dir
setfacl -d -m u:bob:rwx my_dir     # -d sets the *default* ACL → applies to new files

# Revoke bob's access
setfacl -x u:bob my_dir

# Wipe all extended ACLs (keep base chmod perms)
setfacl -b my_dir
```

Heads-up: `setfacl -d` (default ACL) only affects files created **after** you set it — pre-existing files keep their old perms until you re-apply with `-R`.

## VSCode debugging

VSCode Remote-SSH is the most ergonomic way to work on a cluster, but it fails to connect in two annoying-but-easy-to-fix ways.

**Issue 1: man-in-the-middle warning / host key mismatch**

Clusters rotate the public-facing login node's host key every so often (re-imaging, load balancer rotation, etc.). Your local `~/.ssh/known_hosts` still has the old fingerprint, so SSH refuses to connect and VSCode bails with a "REMOTE HOST IDENTIFICATION HAS CHANGED" / man-in-the-middle warning.

Fix — either drop the stale entry once:

```bash
ssh-keygen -R <hostname>     # e.g. ssh-keygen -R greene.hpc.nyu.edu
```

…or, for clusters where the key rotates frequently and you don't care to track it, add this to the host block in `~/.ssh/config` so the check is skipped permanently:

```
Host my-hpc
    HostName my-hpc.example.edu
    User <you>
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

**Issue 2: VSCode can't connect but terminal `ssh` works**

Symptom: `ssh my-hpc` from a regular terminal works fine, but VSCode Remote-SSH hangs at "Setting up SSH host…" or fails to install/start the remote server. Almost always a corrupted `~/.vscode-server` install on the cluster — interrupted downloads, version skew after a VSCode update, leftover lock files.

Fix — wipe it and reconnect:

```bash
ssh my-hpc
rm -rf ~/.vscode-server
exit
```

Then retry Remote-SSH from VSCode; it will reinstall the server cleanly.

## My Config file

A copy of my personal `~/.bashrc` lives at [`.bashrc`](./.bashrc). It's grouped into five sections of shortcuts I rely on across every HPC I touch:

- **General aliases** — `vrc` / `src` to edit & reload bashrc, `lsdu` for per-dir disk usage, `lsfn` for per-dir file counts.
- **GPU cmds** — `nv` (= `nvidia-smi`), and `nvcl` to `kill -9` every process currently holding a GPU.
- **Slurm cmds** — `sq` (my own queued jobs), `sp` (priority), `show <jobid>` (compact job summary), `gpu <cpus> <mem> <hours> <ngpu>` and `cpu <cpus> <mem> <hours>` for one-line interactive `srun` sessions.
- **tmux cmds** — `tmls`, `tma`, `tmkill`, `tmname`. Each takes either a session name or its 1-based index in `tmls`, e.g. `tma 2` attaches the second listed session.
- **screen cmds** — `scls`, `scr`, `sckill`, `scname`, same calling convention as the tmux ones.

Drop it into `~/.bashrc` (or `source` it from there) and reload with `src`.

## Quick login

**ssh-key files**

For clusters that *don't* enforce Duo / Microsoft / OTP on every login (e.g. NYU Torch from inside the campus network, most lab-owned clusters), a public-key login is the fastest path: no password prompt, no 2FA tap, just `ssh my-hpc` and you're in.

Generate a fresh ed25519 key locally (one key per cluster is a good habit — easy to revoke):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_<cluster> -C "<you>@<cluster>"
# leave the passphrase blank for fully passwordless, or set one + use ssh-agent
```

Copy the public half to the cluster — `ssh-copy-id` does the right thing in one shot (it appends to `~/.ssh/authorized_keys` and fixes permissions):

```bash
ssh-copy-id -i ~/.ssh/id_ed25519_<cluster>.pub <you>@<cluster>.example.edu
```

If `ssh-copy-id` isn't available, the manual equivalent:

```bash
cat ~/.ssh/id_ed25519_<cluster>.pub | ssh <you>@<cluster>.example.edu \
    'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

Finally, wire up a short alias in `~/.ssh/config` so you can type `ssh my-hpc` instead of the full hostname:

```
Host my-hpc
    HostName <cluster>.example.edu
    User <you>
    IdentityFile ~/.ssh/id_ed25519_<cluster>
    IdentitiesOnly yes
```

`IdentitiesOnly yes` is worth including — without it, SSH offers every key in `~/.ssh` to the server, which can trip rate-limits or land you on the wrong identity on shared/lab accounts.

**Ignition**

For clusters that *do* force Duo or Microsoft 2FA on every connection, a plain SSH key isn't enough — you'd still tap your phone every time. The fix is an **SSH master / control connection**: authenticate once (password + Duo), then reuse that same TCP tunnel for every subsequent `ssh` / `scp` / `rsync` / VSCode Remote-SSH session.

I wrote a small tool, **[Ignition-sh](https://github.com/wenboluu/Ignition)**, that wraps this pattern into a one-command setup. See the repo for installation and usage — once it's running, repeat logins to the same cluster are instant.

## Connecting computing nodes to the internet

On many HPCs (NYU Greene, NYUSH HPC, etc.) compute nodes have **no outbound internet** — only the login node does. This is deliberate firewalling, so the intended workflow is to pre-stage datasets, models, and `pip` installs on the login node, then run the job.

If you really do need internet on a compute node(e.g. `huggingface` model / dataset downloads mid-run, live `wandb` logging, or a quick `pip install`), the trick is to tunnel its traffic through the login node via an SSH SOCKS proxy. 

See [`examples/compute_node_internet.sh`](./examples/compute_node_internet.sh) — `source` it inside your `srun` / `sbatch` session and `pip` / `wandb` / `huggingface_hub` will route through the login node.

<details>
<summary>Caveats</summary>

- **HTTP(S) only.** The proxy only intercepts traffic from clients that respect `http_proxy` / `https_proxy` — so `pip`, `curl`, `wandb`, `huggingface_hub`, and `git clone https://github.com/…` work, but `git clone git@github.com:…` (raw SSH on port 22) does **not**. For GitHub specifically, prefer the HTTPS URL while the proxy is active.
- **If something on your node stops connecting after sourcing the script** (e.g. an in-cluster service that's now being misrouted through the proxy), undo it with:
  ```bash
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
  ```

</details>

## Port forwarding for local websites

Sometimes you run a web UI on a compute node — Jupyter, TensorBoard, ComfyUI, vLLM's playground, a Gradio demo — and want to open it in your laptop's browser. The compute node isn't reachable from outside the cluster, so you chain two SSH tunnels: **compute → login**, then **login → laptop**.

Say ComfyUI is serving on `<compute-node>:8188`:

```bash
# Step 1 — on the login node: forward login:8188 → compute:8188
ssh -fNL 8188:localhost:8188 <compute-node>

# Step 2 — on your laptop: forward localhost:8188 → login:8188
ssh -fNL 8188:localhost:8188 my-hpc
```

Now open `http://localhost:8188` on your laptop. You can collapse both hops into one command from your laptop using a `ProxyJump`:

```bash
ssh -fNL 8188:localhost:8188 -J my-hpc <compute-node>
```

Tear down with `pkill -f 'ssh -fNL 8188'` on whichever machine you started the tunnel on.

## Other resources
- [missing-semester](https://missing.csail.mit.edu/)
- [Ignition](https://github.com/wenboluu/Ignition)