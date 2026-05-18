from __future__ import annotations

import fnmatch
import threading
import time
from pathlib import Path

from rich.console import Console
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import Config
from .sync import push

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
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.log("[yellow]stopping[/]")
    finally:
        observer.stop()
        observer.join()
