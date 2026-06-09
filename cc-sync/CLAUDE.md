## Working with ccsync (local mirror ⇄ remote workspace)

If a `.ccsync.toml` exists at the repo root, this checkout is the **local
mirror** of a remote workspace. Work that must run on the remote (anything
needing the remote's hardware, data, or environment — not the laptop) runs
there, not locally. Read `.ccsync.toml` and use:

- **`[remote] host` and `path`** — the SSH target and the remote repo root
  (e.g. `host = "login.example.edu"`, `path = "/scratch/<user>/<repo>"`).
  These are your `ssh <host>` destination and the `cd` target on the remote.
- **`[compute]` block (optional)** — if present, it names a compute node to
  hop to. Run the actual command on the compute node, not the login node,
  via a nested ssh. Use `[compute] path` if set, otherwise fall back to
  `[remote] path` (the filesystem is typically shared across login/compute):

  ```
  ssh <remote.host> "ssh <compute.host> 'cd <compute.path or remote.path> && <command>'"
  ```

- **`[sync] exclude`** — paths ccsync does NOT push. Anything matching this
  list must be copied to the remote manually (`scp`/`rsync`) when it changes;
  `ccsync push` will silently skip it. (If a remote cache keys off such files,
  clear that cache after copying.)

### Editing and syncing

- **Edit source files locally only — never edit directly on the remote.**
  Local changes reach the remote either through the ccsync watcher (if it's
  running) or via an explicit push.
- **To sync, prefer `ccsync push`** — run it from the repo root in the
  `cc-sync` conda env:

  ```
  conda activate cc-sync && ccsync push
  ```

  It rsyncs local → remote per `.ccsync.toml`, honoring `[sync] exclude`.
- Before running anything on the remote, either confirm the watcher is active
  or run `ccsync push` (and manually copy any `exclude`d paths you touched).

### Long-running remote work

- **ALWAYS launch long-running remote work inside a named `tmux` session** on
  the remote — not bare `nohup` and not detached job-queue waiters (these have
  been seen to die mid-run and silently stall). A `tmux` session survives SSH
  disconnect *and* local-PC shutdown (the work runs on the remote) and stays
  re-attachable for monitoring:

  ```
  ssh <remote.host> "tmux new-session -d -s <name> 'cd <path> && bash <launcher>.sh'"
  ssh <remote.host> "tmux capture-pane -pt <name> | tail"   # peek at output
  ssh <remote.host> "tmux ls"                                # list sessions
  ```

Skipping the remote hop will either fail (the dependency/hardware isn't on the laptop) or run in the wrong place (e.g. on a login node).