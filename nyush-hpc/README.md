<p align="center">
  <img src="assets/nyush_header.svg" alt="NYUSH HPC" height="90">
</p>


This is an introduction to the NYU Shanghai HPC

## Accees NYUSH HPC \& Access GPUs

Surprisingly, the access to NYU Shanghai HPC and NYUSH HPC GPUs are separated:
- to access NYU Shanghai HPC, plz visit [here](https://support.nyu.edu/esc?id=sc_cat_item&table=sc_cat_item&sys_id=7b9e64ce1bd912108ef92f81b24bcb2e&searchTerm=hpc%20shanghai) and fill out the form.
- to access the GPUs, you need to email [shanghai.it.help@nyu.edu](mailto:shanghai.it.help@nyu.edu) or [Guangchao Hu](mailto:gh2440@nyu.edu). At the time this doc is written (2026.5.22), [Guangchao Hu](mailto:gh2440@nyu.edu) and [Dr. Tam](yt2267@nyu.edu) are in charge of the Shanghai HPC and students still need to manually request the GPU access.

## GPU resources

Since the Shanghai HPC is an HPC in China, the types of accessible GPUs are limited. The main GPU types on the Shanghai HPC are mainly A800 and H20. Below is a comparison between A800, H20, and other common GPU types (numbers are for the SXM form factor; PCIe variants are slightly lower):

| GPU      | Arch   | VRAM        | Mem. BW   | FP16/BF16 | FP8       | NVLink   | TDP   | Notes                                  |
| -------- | ------ | ----------- | --------- | --------- | --------- | -------- | ----- | -------------------------------------- |
| A100     | Ampere | 80 GB HBM2e | 2.0 TB/s  | 312 TF    | —         | 600 GB/s | 400 W | Reference Ampere flagship              |
| **A800** | Ampere | 80 GB HBM2e | 2.0 TB/s  | 312 TF    | —         | 400 GB/s | 400 W | China-export A100; NVLink BW cut by ⅓  |
| H100     | Hopper | 80 GB HBM3  | 3.35 TB/s | 989 TF    | 1,979 TF  | 900 GB/s | 700 W | Reference Hopper flagship              |
| **H20**  | Hopper | 96 GB HBM3  | 4.0 TB/s  | ~148 TF   | ~296 TF   | 900 GB/s | 400 W | China-export Hopper; compute ≈ 1/7 H100, but **more VRAM** than H100 |
| H200     | Hopper | 141 GB HBM3e| 4.8 TB/s  | 989 TF    | 1,979 TF  | 900 GB/s | 700 W | Same compute as H100, much more VRAM   |

Practical takeaways for the Shanghai HPC's A800 / H20 mix:

- **A800 is your compute workhorse.** Same FP16/BF16 throughput as a regular A100 — only the inter-GPU NVLink bandwidth is reduced. Fine for single-node training; multi-node / heavy tensor-parallel may bottleneck on the slower NVLink.
- **H20 is memory-rich but compute-poor.** It has *more* VRAM than a base H100 (96 GB vs 80 GB) and an entire HBM3 memory subsystem, but its tensor-core throughput is roughly **1/7** of an H100. Best suited for **inference / long-context / KV-cache-heavy serving** rather than pre-training.
- **No FP8 on A800.** FP8 (and the Transformer Engine) is Hopper-only — if you need it, you're on H20.

There are rumours that H200s will be available on NYU Shanghai HPC, but the available date is not quite clear.

## System module versions

Some module versions on NYUSH HPC are somewhat outdated. For instance, `glibc` is or version 2.28.

A key consequence about this is: prebuilt-wheels of `flash-attention` will not work. You can not do:
```bash
pip install flash-attn==2.8.3
# or
wget https://github.com/mjun0812/flash-attention-prebuild-wheels/releases/download/v0.7.16/flash_attn-2.8.3+cu128torch2.8-cp311-cp311-linux_x86_64.whl
pip install flash_attn-2.8.3+cu128torch2.8-cp311-cp311-linux_x86_64.whl
```
Because they depend on `glibc>=2.32`. Instead, `flash-attn` has to be installed from source:
```bash
git clone https://github.com/Dao-AILab/flash-attention
cd flash-attention
git checkout v2.8.3
export TORCH_CUDA_ARCH_LIST="8.0;9.0"
export FLASH_ATTENTION_FORCE_BUILD=TRUE
MAX_JOBS=8 pip install --no-binary :all: --no-build-isolation --no-cache-dir --verbose .
```

There might be other packages that have version problems. If you find any, plz open an issue or PR.

However, Guangchao told me there would be a thorough maintenance and update of the NYU Shanghai HPC at some time, so maybe this issue will eventually get fixed.

## Connecting computing nodes to the internet

NYU Shanghai HPC is one of the HPCs where computing nodes have no internet access. To address this, plz refer to [here](../hpcs-general/README.md#connecting-computing-nodes-to-the-internet).

## Other resources
- [NYUSH HPC docs](https://ood.shanghai.nyu.edu/hpc/)