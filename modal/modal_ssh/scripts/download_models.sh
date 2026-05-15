#!/bin/bash
# Download HuggingFace models from the `heavyball` org into the HF cache.
# Run inside the Modal VM — HF_TOKEN is already in the env via huggingface-secret,
# and /root/.cache/huggingface is a persistent Volume, so re-runs are free.
#
# Usage:
#   ./scripts/download_models.sh              # uses MODELS list below
#   ./scripts/download_models.sh foo bar      # overrides the list

set -e

ORG="${ORG:-heavyball}"

# Edit this list.
MODELS=(
    sdar-1.7b-mrp-3lyr
    sdar-4b-mrp-3lyr
    sdar-8b-mrp-3lyr
    sdar-1.7b-mrp-3lyr-direct
    sdar-4b-mrp-3lyr-direct
    sdar-8b-mrp-3lyr-direct
)

if [ "$#" -gt 0 ]; then
    MODELS=("$@")
fi

if [ "${#MODELS[@]}" -eq 0 ]; then
    echo "No models specified. Edit MODELS in $0 or pass names as args." >&2
    exit 1
fi

for name in "${MODELS[@]}"; do
    echo
    echo "→ $ORG/$name"
    git clone "https://huggingface.co/$ORG/$name"
done
