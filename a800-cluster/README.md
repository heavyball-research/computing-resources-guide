# A800 Cluster

Two 8×A800 boxes — `175.102.130.109` and `175.102.130.93`. They
**can't reach the international internet** (`huggingface.co`, `pypi.org`,
`github.com` all time out), but **Chinese mirrors are reachable directly**. Point
everything at the mirrors and you never need the (slow, 200 GB/mo capped) proxy.

## Set up the mirrors (once per box)

```bash
# pip -> Tsinghua (tuna). pip.conf is read by every pip invocation, any shell.
# (A fresh box may lack pip: sudo apt-get install -y python3-pip python3.10-venv)
python3 -m pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# conda -> Tsinghua channels
cat > ~/.condarc <<'EOF'
default_channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
EOF

# Hugging Face -> hf-mirror.com. Put these ABOVE the `case $- in *i*) ... return`
# line in ~/.bashrc, so non-interactive shells (tmux launchers) see them too.
export HF_ENDPOINT=https://hf-mirror.com
export PATH="$HOME/.local/bin:$PATH"     # for pip --user binaries (hf, uv, ...)
```

That covers pip, conda, and Hugging Face. The rest are used per-command:

| Need | Mirror | How |
|------|--------|-----|
| PyTorch CUDA wheels | `download.pytorch.org` | `pip install torch --extra-index-url https://download.pytorch.org/whl/cu130` |
| pip pkgs tuna lacks (e.g. `*-nightly`) | `mirrors.aliyun.com` | add `--extra-index-url https://mirrors.aliyun.com/pypi/simple` |
| `git clone` / GitHub release | `ghfast.top` | prefix the URL: `git clone https://ghfast.top/https://github.com/<org>/<repo>` |
| Models / datasets | `hf-mirror.com` | `hf download <repo_id> --local-dir <dir>` (uses `HF_ENDPOINT` above) |

Proxy fallback — only for something with no mirror (unstable, capped):
```bash
export https_proxy=http://10.20.20.18:7890 http_proxy=http://10.20.20.18:7890 no_proxy=127.0.0.1,localhost
```
