# Modal

## What is Modal?

Modal is a serverless cloud platform for running code (training, inference, batch jobs, dev environments) on on-demand GPUs and CPUs. You describe the container, hardware, and entrypoint in Python; Modal provisions a fresh VM per run, streams logs back, and tears it down when you're done — billed by the second.

**VM ≠ HPC.** An HPC cluster (SLURM/PBS) is a shared, queue-scheduled pool of long-lived nodes with a shared filesystem, MPI fabric, and admin-curated software stack — great for tightly-coupled multi-node jobs, painful for fast iteration. Modal gives you an isolated, ephemeral VM per job with your own container image, no queue wait, and no shared state — great for iteration, elastic scaling, and reproducibility; not built for low-latency multi-node interconnect.

## modal-ssh CLI

A YAML-driven CLI we added on top of Modal for spinning up dev VMs and submitting batch jobs from the same config. `up` opens a VSCode Remote-SSH window into a live container; `run` fires off a bash script in the background. See [`modal_ssh/`](./modal_ssh/).

## Other resources
- [modal docs](https://modal.com/docs)
- [modal-auto-research-skills](https://github.com/modal-projects/modal-auto-research-skills)