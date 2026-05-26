#!/usr/bin/env python3
"""
Per-GPU CUDA keepalive for training jobs with alternating GPU activity.

Runs persistent worker threads that continuously do matrix multiplications.
The main thread periodically checks nvidia-smi and pauses/resumes workers
so there are no gaps in GPU utilization from subprocess overhead.

Designed for GRPO-style training where learner GPUs and vLLM rollout GPUs
alternate activity, causing half the GPUs to appear idle at any time.
"""

import argparse
import subprocess
import threading
import time
import signal
import sys

import torch


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[cuda-keepalive {ts}] {msg}", flush=True)


def get_per_gpu_utilization() -> list[int] | None:
    """Return list of per-GPU utilization % via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5,
        )
        return [int(line.strip()) for line in out.strip().splitlines()]
    except Exception:
        return None


def allocate_buffers(
    gpu_ids: list[int], dim: int,
) -> dict[int, tuple[torch.Tensor, torch.Tensor]]:
    """Pre-allocate square matrices on each GPU for keepalive matmuls."""
    buffers = {}
    for gid in gpu_ids:
        try:
            dev = torch.device(f"cuda:{gid}")
            a = torch.randn(dim, dim, device=dev, dtype=torch.float32)
            b = torch.randn(dim, dim, device=dev, dtype=torch.float32)
            buffers[gid] = (a, b)
            mem_mb = 2 * a.nelement() * a.element_size() / (1024 * 1024)
            log(f"GPU {gid}: allocated 2x {dim}x{dim} float32 matrices ({mem_mb:.0f} MB)")
        except Exception as e:
            log(f"GPU {gid}: cannot allocate buffer ({e}), skipping")
    return buffers


def gpu_worker(
    gpu_id: int,
    buffers: dict[int, tuple[torch.Tensor, torch.Tensor]],
    active: threading.Event,
    stop: threading.Event,
):
    """Persistent worker: matmuls while active is set, sleeps otherwise."""
    a, b = buffers[gpu_id]
    while not stop.is_set():
        if active.is_set():
            torch.mm(a, b)
        else:
            stop.wait(timeout=0.1)


def main():
    p = argparse.ArgumentParser(description="Per-GPU CUDA keepalive")
    p.add_argument("--target-util", type=int, default=50,
                    help="Target GPU utilization %% (default: 50)")
    p.add_argument("--poll-interval", type=float, default=2.0,
                    help="Seconds between nvidia-smi checks (default: 2.0)")
    p.add_argument("--matrix-dim", type=int, default=2000,
                    help="Dimension of square matrices for keepalive matmuls (default: 2000)")
    p.add_argument("--gpu-ids", type=str, default=None,
                    help="Comma-separated GPU IDs to manage (default: all visible)")
    p.add_argument("--startup-delay", type=int, default=30,
                    help="Seconds to wait before starting (let training initialize) (default: 30)")
    args = p.parse_args()

    stop_event = threading.Event()

    def shutdown(*_):
        stop_event.set()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if args.gpu_ids is not None:
        gpu_ids = [int(x) for x in args.gpu_ids.split(",")]
    else:
        n = torch.cuda.device_count()
        gpu_ids = list(range(n))

    log(f"Managing GPUs: {gpu_ids}")
    log(f"Target utilization: {args.target_util}%")
    log(f"Waiting {args.startup_delay}s for training to initialize ...")
    time.sleep(args.startup_delay)

    buffers = allocate_buffers(gpu_ids, args.matrix_dim)
    if not buffers:
        log("No GPU buffers allocated, exiting")
        sys.exit(1)

    active_flags: dict[int, threading.Event] = {}
    for gid in gpu_ids:
        if gid not in buffers:
            continue
        flag = threading.Event()
        flag.set()  # start active
        active_flags[gid] = flag
        t = threading.Thread(
            target=gpu_worker,
            args=(gid, buffers, flag, stop_event),
            daemon=True,
        )
        t.start()

    log("Keepalive active — all workers running")

    while not stop_event.is_set():
        time.sleep(args.poll_interval)

        utils = get_per_gpu_utilization()
        if utils is None:
            log("Cannot read nvidia-smi, retrying ...")
            continue

        status = []
        for gid in gpu_ids:
            if gid >= len(utils) or gid not in active_flags:
                continue
            util = utils[gid]
            if util >= args.target_util:
                active_flags[gid].clear()
                status.append(f"GPU {gid}: {util}% (paused)")
            else:
                active_flags[gid].set()
                status.append(f"GPU {gid}: {util}% (active)")

        log(" | ".join(status))


if __name__ == "__main__":
    main()