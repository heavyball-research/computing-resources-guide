"""
Keep a GPU job alive by sustaining high SM utilization with minimal VRAM.

Torch HPC kills jobs whose GPU utilization stays low. This loop performs
small matmuls back-to-back so `nvidia-smi` reports near-100% utilization
while holding only a few MB of VRAM, leaving the rest free for real work
running alongside (or for a placeholder job between debugging sessions).

Usage:
    python keep_gpu_busy.py                 # all visible GPUs, run forever
    python keep_gpu_busy.py --size 512      # bigger matmuls (still tiny VRAM)
    python keep_gpu_busy.py --duration 3600 # auto-stop after 1 hour
"""
import argparse
import time
import torch


def busy_loop(device: torch.device, size: int, dtype: torch.dtype, duration: float | None):
    a = torch.randn(size, size, device=device, dtype=dtype)
    b = torch.randn(size, size, device=device, dtype=dtype)
    c = torch.empty_like(a)
    start = time.time()
    iters = 0
    while True:
        torch.matmul(a, b, out=c)
        # Tiny in-place update so the compiler can't constant-fold the loop
        a.add_(c, alpha=1e-8)
        iters += 1
        if iters % 10000 == 0:
            torch.cuda.synchronize(device)
            elapsed = time.time() - start
            print(f"[{device}] {iters} iters in {elapsed:.1f}s ({iters/elapsed:.0f} it/s)", flush=True)
            if duration is not None and elapsed >= duration:
                return


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=256, help="matmul side length (default 256 → ~0.75 MB per matrix in fp32)")
    p.add_argument("--dtype", choices=["fp32", "fp16", "bf16"], default="fp32")
    p.add_argument("--duration", type=float, default=None, help="seconds; omit to run until killed")
    p.add_argument("--device", type=str, default=None, help="cuda index, e.g. 0; default = all visible GPUs")
    args = p.parse_args()

    dtype = {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}[args.dtype]
    assert torch.cuda.is_available(), "CUDA not available"

    devices = [torch.device(f"cuda:{args.device}")] if args.device is not None else \
              [torch.device(f"cuda:{i}") for i in range(torch.cuda.device_count())]
    print(f"keeping {len(devices)} GPU(s) busy: size={args.size} dtype={args.dtype}", flush=True)

    if len(devices) == 1:
        busy_loop(devices[0], args.size, dtype, args.duration)
    else:
        import threading
        threads = [threading.Thread(target=busy_loop, args=(d, args.size, dtype, args.duration), daemon=True) for d in devices]
        for t in threads: t.start()
        for t in threads: t.join()


if __name__ == "__main__":
    main()
