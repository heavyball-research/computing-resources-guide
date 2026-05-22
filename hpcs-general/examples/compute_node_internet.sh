#!/bin/bash
# compute_node_internet.sh
#
# Give a compute node outbound internet by tunneling through the login node.
# Run this *inside* your srun / sbatch session on the compute node.
#
# How it works:
#   1. We open a background SSH connection back to the login node with
#      `-D <port>`, which exposes a local SOCKS5 proxy at localhost:$PORT.
#   2. Any process that respects http_proxy / https_proxy (pip, curl,
#      wandb, huggingface_hub, requests, …) will route its traffic through
#      that SOCKS proxy, which exits the firewall via the login node's
#      already-allowed route.
#
# Prereq: passwordless SSH from compute node → login node (key in
#         ~/.ssh/authorized_keys on the login node — usually already set
#         up since they share $HOME).

set -euo pipefail

LOGIN_HOST="${LOGIN_HOST:-login-node}"   # change to your cluster's login host
PORT="${PORT:-1080}"

# 1. Open the SOCKS proxy (backgrounded, no remote command).
#    -f = fork into background, -N = don't run a remote command,
#    -D = dynamic application-level port forwarding (SOCKS).
ssh -fN -D "$PORT" \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=60 \
    "$LOGIN_HOST"

# 2. Point HTTP/HTTPS env vars at the local SOCKS proxy.
#    `socks5h://` (note the `h`) makes the proxy resolve DNS too, which
#    matters because the compute node usually can't resolve external
#    hostnames either.
export http_proxy="socks5h://localhost:$PORT"
export https_proxy="socks5h://localhost:$PORT"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
# Bypass the proxy for in-cluster traffic.
export no_proxy="localhost,127.0.0.1,.local,.internal"
export NO_PROXY="$no_proxy"

echo "[compute_node_internet] SOCKS proxy up on localhost:$PORT via $LOGIN_HOST"
echo "[compute_node_internet] http_proxy / https_proxy exported in this shell"
echo
echo "Quick test:"
echo "    curl -sS https://ifconfig.me   # should now return the login node's IP"
echo
echo "To tear down later:"
echo "    pkill -f 'ssh -fN -D $PORT'"
