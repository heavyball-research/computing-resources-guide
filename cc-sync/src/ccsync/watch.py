from __future__ import annotations

import fnmatch
import threading
import time
from pathlib import Path

from rich.console import Console
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import Config
from .sync import mirror_logs, pull, push

console = Console()


def _is_excluded(rel: str, patterns: list[str]) -> bool:
    parts = rel.split("/")
    for pat in patterns:
        norm = pat.rstrip("/")
        if fnmatch.fnmatch(rel, norm) or fnmatch.fnmatch(rel, pat):
            return True
        if any(fnmatch.fnmatch(p, norm) for p in parts):
            return True
    return False


class _Handler(FileSystemEventHandler):
    def __init__(self, cfg: Config, fire):
        self.cfg = cfg
        self.fire = fire
        self.root = cfg.project_root.resolve()

    def on_any_event(self, event: FileSystemEvent) -> None:
        try:
            rel = Path(event.src_path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return
        if _is_excluded(rel, self.cfg.sync.exclude):
            return
        self.fire(rel)


def run_watcher(cfg: Config) -> None:
    debounce = max(cfg.sync.debounce_ms, 50) / 1000.0
    lock = threading.Lock()
    timer: list[threading.Timer | None] = [None]
    pending: set[str] = set()

    def do_push():
        with lock:
            paths = list(pending)
            pending.clear()
            timer[0] = None
        console.log(f"[cyan]push[/] ({len(paths)} change{'s' if len(paths) != 1 else ''})")
        rc = push(cfg)
        if rc != 0:
            console.log(f"[red]rsync exited {rc}[/]")

    def fire(rel: str):
        with lock:
            pending.add(rel)
            if timer[0] is not None:
                timer[0].cancel()
            t = threading.Timer(debounce, do_push)
            t.daemon = True
            timer[0] = t
            t.start()

    handler = _Handler(cfg, fire)
    observer = Observer()
    observer.schedule(handler, str(cfg.project_root), recursive=True)
    observer.start()
    console.log(f"[green]watching[/] {cfg.project_root} → {cfg.remote.host}:{cfg.remote.path}")

    stop_event = threading.Event()
    log_thread: threading.Thread | None = None
    interval = cfg.sync.log_pull_interval_s
    if interval > 0:
        def log_loop():
            while not stop_event.wait(interval):
                rc = mirror_logs(cfg)
                if rc != 0:
                    console.log(f"[red]log mirror exited {rc}[/]")
        log_thread = threading.Thread(target=log_loop, daemon=True)
        log_thread.start()
        console.log(f"[cyan]mirroring remote logs every {interval}s → logs/cc-sync/[/]")

    # Periodic full pull of [pull].paths from remote (logs/, outputs/, etc.).
    # Independent of the log mirroring above; configured via [pull].interval_s.
    pull_thread: threading.Thread | None = None
    pull_interval = cfg.pull.interval_s
    pull_paths = list(cfg.pull.paths)
    if pull_interval > 0 and pull_paths:
        def pull_loop():
            while not stop_event.wait(pull_interval):
                console.log(f"[cyan]pull[/] ({', '.join(pull_paths)})")
                rc = pull(cfg, quiet=True)
                if rc != 0:
                    console.log(f"[red]pull exited {rc}[/]")
        pull_thread = threading.Thread(target=pull_loop, daemon=True)
        pull_thread.start()
        console.log(
            f"[cyan]pulling {pull_paths} every {pull_interval}s remote → local[/]"
        )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.log("[yellow]stopping[/]")
    finally:
        stop_event.set()
        observer.stop()
        observer.join()
        if log_thread is not None:
            log_thread.join(timeout=2)
        if pull_thread is not None:
            pull_thread.join(timeout=2)
