from ccsync.config import Config, PullCfg, RemoteCfg, RunCfg, SyncCfg
from ccsync.sync import build_pull_cmd, build_push_cmd


def test_push_includes_excludes_and_delete(cfg):
    cmd = build_push_cmd(cfg)
    assert cmd[0] == "rsync"
    assert "-avzh" in cmd
    assert "--delete" in cmd
    assert "--exclude=.git/" in cmd
    assert "--exclude=__pycache__/" in cmd
    assert "--exclude=*.ncu-rep" in cmd
    assert cmd[-2].endswith("/")  # local has trailing slash
    assert cmd[-1] == "myhost:/home/me/proj/"
    assert "-e" in cmd and cmd[cmd.index("-e") + 1] == "ssh"


def test_push_dry_run(cfg):
    cmd = build_push_cmd(cfg, dry_run=True)
    assert "--dry-run" in cmd


def test_push_no_delete(cfg):
    cfg.sync.delete = False
    cmd = build_push_cmd(cfg)
    assert "--delete" not in cmd


def test_pull_per_path(cfg):
    cmds = build_pull_cmd(cfg)
    assert len(cmds) == 2
    assert cmds[0][-2] == "myhost:/home/me/proj/logs/"
    assert cmds[0][-1].endswith("/logs/")
    assert cmds[1][-2] == "myhost:/home/me/proj/artifacts/"


def test_pull_override_paths(cfg):
    cmds = build_pull_cmd(cfg, paths=["custom/"])
    assert len(cmds) == 1
    assert cmds[0][-2] == "myhost:/home/me/proj/custom/"


def test_push_with_user_port_identity(tmp_path):
    cfg = Config(
        project_root=tmp_path,
        remote=RemoteCfg(
            host="h", path="/p", user="ubuntu", port=2222,
            identity_file="/k/id",
        ),
        sync=SyncCfg(), pull=PullCfg(), run=RunCfg(),
    )
    cmd = build_push_cmd(cfg)
    i = cmd.index("-e")
    assert cmd[i + 1] == "ssh -p 2222 -i /k/id"
    assert cmd[-1] == "ubuntu@h:/p/"
