#!/bin/bash
# Example non-interactive training recipe. Uploaded into the container at
# launch and executed by `run_batch`. Edits to this file are picked up
# instantly — they do NOT bust the modal image cache.
set -e

# Non-interactive bash skips most of .bashrc, so conda init never runs. Source
# it explicitly here before invoking the training script (which calls `conda`).
source /root/miniconda3/etc/profile.d/conda.sh
conda activate llamafactory_sdar

cd /root/multi-token-residual-prediction

export MODEL_PATH='heavyball/sdar-1_7b-mrp-3lyr'
export NUM_GPUS=8
export micro_bs=2
export loss_type=kd_diff
export reveal_mode=gt
export gt_topk=1
export mtp_steps=3
export loss_weight_mode=uniform
export mtp_init_std=0.2
export LR=1e-3
export freeze_backbone=True
export freeze_lm_head=True
export override=False

bash scripts/train_sdar_mrp.sh
