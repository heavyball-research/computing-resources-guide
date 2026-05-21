<p align="center">
  <img src="assets/torch_header.svg" alt="NYU Torch HPC" height="90">
</p>

This section aims to discuss the special properties of NYU Torch HPC. For general large scale shared HPC guide, see [hpcs-general](../hpcs-general/).

## Logging into Torch HPC
The authentication process of Torch HPC is quite special. Normally you will be prompted to open a Microsoft authentication window, copy and paste a transient auth code, and log in via your NYU account:
```bash
# example
(yx3038@login.torch.hpc.nyu.edu) 
Authenticate with PIN XXXXXXXXX at 
https://login.microsoft.com/device and press ENTER.
```
<p align="center">
  <img src="assets/microsoft-login.png" alt="Microsoft device login" width="500">
</p>

This can take a lot of time and is very annoying each time you switch to a new working directory. 

Fortunately, [Wenbo Lu](wenboluu.github.io) (a.k.a General LucArthur) has developed a lightweight tool [Ignition](https://github.com/wenboluu/Ignition) that exploits `expect` and master connection so you can log in once and then you can access the Torch HPC without extra authetication for a long period.

If you think this may save your time, plz check the guide in Ignition.

<details>
<summary><em>Note</em></summary>

In my experience sometimes trying `ignite` the first time returns
```bash
→ Auth may have failed or connection not ready.
```
Don't panic in such cases. Simply retry several times and you'll be able to log in:
```bash
→ SSH session ready. You're in.
```

</details>

## Projects \& Priority
The GPU types you can request and the priority of your requests are determined by **account** and **partition**. Of course when a job gets started are also determined by size, timestamp, fairshare, and dependencies.   
Currently, the Heavyball has been granted 4 accounts:
- `torch_pr_976_general, torch_pr_1030_general`: general account, lowest priority, unable to access A100 and H100.
- `torch_pr_1030_tandon_priority`: highest priority, but unable to access `h200_tandon`.
- `torch_pr_1030_tandon_advanced`: medium priority, able to access H200.

Below is a valid account-partition matrix:
| Account                         | A100          | H100          | H200                         |
| ------------------------------- | ------------- | ------------- | ---------------------------- |
| `torch_pr_976_general, torch_pr_1030_general`         | —             | —             | `h200_public` only           |
| `torch_pr_1030_tandon_advanced` | `a100_tandon` | `h100_tandon` | `h200_public`, `h200_tandon` |
| `torch_pr_1030_tandon_priority` | `a100_tandon` | `h100_tandon` | `h200_public` only           |

There are also many partitions we cannot access:
- `a100_cilvr` → CILVR lab only
- `a100_cds, h200_cds` → Center for Data Science only
- `a100_chemistry, h200_courant` → those departments only
- `h200_bpeher` → a specific PI's allocation
- `a100, h100, h200, *_plus` → likely require a special QOS or a different allocation account

Of course the available projects are subject to changes. You may visit the [torch projects website](https://projects.hpc.nyu.edu/project) to see your available projects.

## Low GPU utilization
The Slurm system on Torch kills jobs with low GPU utilization. To prevent this during debugging, idle waits, or checkpoint reloads, run [`examples/keep_gpu_busy.py`](examples/keep_gpu_busy.py) alongside your real work — it loops small matmuls to keep `nvidia-smi` reporting ~100% util while using only a few MB of VRAM, leaving the rest free for the actual job.

```bash
# Cover every GPU in the allocation (one thread per visible device)
python examples/keep_gpu_busy.py &

# Auto-stop after 1 hour
python examples/keep_gpu_busy.py --duration 3600 &

# Pin to a specific GPU
python examples/keep_gpu_busy.py --device 0 &
```

The script honors `CUDA_VISIBLE_DEVICES`, so on a multi-GPU SLURM allocation it covers every granted GPU without extra flags. Background it (`&`, `nohup`, or a separate `tmux` pane) so it doesn't block your shell.

## Torch login node is fragile
Torch login node is very fragile and you might be kicked out for various operations:
1. downloading and installing large packages like `torch`;
2. downloading large models and datasets from huggingface;
3. spawning many processes or using many `watch` to monitor status;
4. running Claude Code/Codex in auto mode (which potentially involves lots of bash command executions);
5. connecting with VSCode and open windows with a huge amount of text or conduct many file operations via the GUI (instead of CLI).

Normally it will be fine to do `5`, just be aware that you might want to use `tail`, `head`, `grep`, `ls`, `vim`, `mv`, `rm`,  to view and operate on your files.

For `1-4`, fortunately the computing nodes on Torch can reach the external network, so a common solution is to request a CPU node, ssh to the CPU node, then these operations on that node. 

## Other resources
- [Torch HPC website](https://www.nyu.edu/life/information-technology/research-computing-services/high-performance-computing/high-performance-computing-nyu-it.html?challenge=d06e90d7-4d8f-4b88-9d8c-10b73beb60f1)
- [Torch HPC docs](https://services.rt.nyu.edu/docs/hpc/getting_started/intro/)
- [Torch HPC projects](https://projects.hpc.nyu.edu/project)
- [Torch HPC cheatsheet](https://github.com/RicercarG/NYU-Torch-HPC-Cheatsheet)
- [Ignition](https://github.com/wenboluu/Ignition)
