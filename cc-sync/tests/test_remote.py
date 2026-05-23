from ccsync.remote import (
    build_attach_cmd,
    build_foreground_cmd,
    build_kill_cmd,
    build_launch_cmd,
    build_list_cmd,
    build_tail_cmd,
    remote_log_path,
    session_name,
)


def test_session_name(cfg):
    assert session_name(cfg, "train") == "ccs-train"


def test_foreground_cmd(cfg):
    cmd = build_foreground_cmd(cfg, ["pytest", "-x"])
    assert cmd[0] == "ssh"
    assert cmd[1] == "myhost"
    inner = cmd[2]
    assert "cd /home/me/proj" in inner
    assert "pytest -x" in inner
    assert inner.startswith("bash -lc ")


def test_launch_cmd_uses_tmux_new_session(cfg):
    cmd = build_launch_cmd(cfg, "train", ["python", "train.py"])
    assert cmd[:2] == ["ssh", "myhost"]
    inner = cmd[2]
    assert "tmux new-session -d -s" in inner
    assert "ccs-train" in inner
    assert "python train.py" in inner
    assert "tee" in inner
    assert "CCSYNC_EXIT=" in inner


def test_attach_uses_pty(cfg):
    cmd = build_attach_cmd(cfg, "train")
    assert cmd[:3] == ["ssh", "-t", "myhost"]
    assert "tmux attach -t" in cmd[3]
    assert "ccs-train" in cmd[3]


def test_kill_cmd(cfg):
    cmd = build_kill_cmd(cfg, "train")
    assert "tmux kill-session -t" in cmd[2]
    assert "ccs-train" in cmd[2]


def test_list_cmd_filters_prefix(cfg):
    cmd = build_list_cmd(cfg)
    assert "tmux ls" in cmd[2]
    assert "ccs-" in cmd[2]


def test_tail_cmd_follow(cfg):
    cmd = build_tail_cmd(cfg, "train", follow=True)
    assert "tail -F" in cmd[2]
    assert remote_log_path(cfg, "train") in cmd[2]


def test_tail_cmd_no_follow(cfg):
    cmd = build_tail_cmd(cfg, "train", follow=False)
    assert "tail " in cmd[2] and "-f" not in cmd[2]
