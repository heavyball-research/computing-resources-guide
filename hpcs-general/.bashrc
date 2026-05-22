alias vrc='vim ~/.bashrc'
alias src='source ~/.bashrc'
alias lsdu='du -d 1 . -h'
alias lsfn='for d in $(find $(pwd) -maxdepth 1 -mindepth 1 -type d | sort -u); do n_files=$(find $d | wc -l); echo $d $n_files; done'

# gpu cmds
alias nv='nvidia-smi'
nvcl() {
  local pids
  pids=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr -d ' ' | sort -u)
  if [ -z "$pids" ]; then
    echo "No GPU processes found."
    return 0
  fi
  echo "Killing GPU PIDs: $(echo "$pids" | tr '\n' ' ')"
  echo "$pids" | xargs -r kill -9
}

# slurm cmds
alias sq="squeue -u $USER -o '%.18i %.10P %.20j %.8T %.19S %.6D %.10M %R' | sort -h"
alias sp="sprio -u $USER"
show() {
    scontrol show job "$1" \
    | grep -Eo 'JobName=[^ ]+|NumNodes=[^ ]+|TRES=[^ ]*gpu=[0-9]+|TimeLimit=[^ ]+|StdOut=[^ ]+|StdErr=[^ ]+' \
    | sed -E '
        s/JobName=/JobName: /;
        s/NumNodes=/NumNodes: /;
        s/TRES=.*gpu=/NumGPUs: /;
        s/TimeLimit=/TimeLimit: /;
        s/StdOut=/StdOut: /;
        s/StdErr=/StdErr: /
    '
}
gpu() {
  srun --nodes=1 --cpus-per-task=$1 --mem=$2GB --time=$3:00:00 --gres=gpu:$4 --mail-type=all --pty /bin/bash
}
cpu() {
  srun --nodes=1 --cpus-per-task=$1 --mem=$2GB --time=$3:00:00 --pty /bin/bash
}

# tmux cmds — arg is a session name or its 1-based index in `tmls`.
_tm_resolve() {
  if [[ "$1" =~ ^[0-9]+$ ]]; then
    tmux ls 2>/dev/null | sed -n "${1}p" | cut -d: -f1
  else
    echo "$1"
  fi
}
tmls()   { tmux ls 2>/dev/null | nl -ba; }
tma()    { local s; s=$(_tm_resolve "$1"); [ -z "$s" ] && { echo "no session: $1"; return 1; }; tmux attach -t "$s"; }
tmkill() { local s; s=$(_tm_resolve "$1"); [ -z "$s" ] && { echo "no session: $1"; return 1; }; tmux kill-session -t "$s"; }
tmname() { local s; s=$(_tm_resolve "$1"); [ -z "$s" ] && { echo "no session: $1"; return 1; }; tmux rename-session -t "$s" "$2"; }

# screen cmds — arg is a session name/id or its 1-based index in `scls`.
_sc_resolve() {
  if [[ "$1" =~ ^[0-9]+$ ]]; then
    screen -ls 2>/dev/null | awk '/^\s*[0-9]+\./ {print $1}' | sed -n "${1}p"
  else
    echo "$1"
  fi
}
scls()    { screen -ls 2>/dev/null | awk '/^\s*[0-9]+\./ {print $0}' | nl -ba; }
scr()     { local s; s=$(_sc_resolve "$1"); [ -z "$s" ] && { echo "no session: $1"; return 1; }; screen -r "$s"; }
sckill()  { local s; s=$(_sc_resolve "$1"); [ -z "$s" ] && { echo "no session: $1"; return 1; }; screen -S "$s" -X quit; }
scname()  { local s; s=$(_sc_resolve "$1"); [ -z "$s" ] && { echo "no session: $1"; return 1; }; screen -S "$s" -X sessionname "$2"; }
