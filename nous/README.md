<p align="center">
  <img src="assets/nous_header.svg" alt="Nous Research" height="90">
</p>

The Nous cluster is a very stable and convenient HPC system - as long as it's not under maintenance. Most of the information you need can be found in [HPC general](../hpcs-general/).

## Long sbatch + backend Jobs
On the Nous cluster we often need to request very long sbatch jobs to guarantee GPU availability. In this case, the typical workflow is like the following:
```bash
# step 1: request a very long sbatch job (14 days or unlimited time)
# for example: 
salloc --nodes=1 --exclusive --gpus=8 --cpus-per-task=96

# step 2: open a tmux or screen session
tmux # or screen

# step 3: attach to the node in the session
srun --jobid=<jobid> --overlap --pty bash

# step 4: run your workload
python train.py
```

I developed a lightweight tool [nohup-queue](https://github.com/Zephyr271828/nohup-queue) to detect available GPUs on the current node and automatically queue and run your jobs in the backend. I find this workflow very suitable with this setting. If you are interested, plz check the repo for details.

## Other resources
- [nohup-queue](https://github.com/Zephyr271828/nohup-queue)